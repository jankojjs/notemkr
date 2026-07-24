"""Pipeline za transkripciju: MP3 -> note.

`transcribe_file` je glavna ulazna tacka celog alata i vraca rezultat-mapu fiksne
seme (vidi docstring funkcije). Jezgro je `extract_notes`: dekodira audio i pusta
Spotify **basic-pitch** (ONNX backend) da iz njega izvuce dogadjaje nota.

Teske zavisnosti (basic-pitch, librosa, pretty_midi) se uvoze lenjivo unutar
funkcija, tako da `import notemkr` ostaje trenutan i bez sporednih efekata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import is_silent, load_audio
from .notes import Note, make_note, sort_notes, velocity_from_amplitude
from .quantize import (
    DEFAULT_BEATS_PER_BAR,
    DEFAULT_GRID,
    analyze_rhythm,
    estimate_key,
    quantize_notes,
    snap_to_scale,
)
from .split_hands import HandSplitParams, split_hands

# --- Podrazumevani parametri modela --------------------------------------------------
# basic-pitch podrazumevano koristi 0.5 / 0.3; za harmoniku (kontinuiran, "trskast"
# ton sa jakim harmonicima) ovi pragovi rade solidno, a izlozeni su kroz parametre.
DEFAULT_ONSET_THRESHOLD = 0.5
DEFAULT_FRAME_THRESHOLD = 0.3
DEFAULT_MIN_NOTE_LENGTH_MS = 100.0

# Odbaci note u koje model nije dovoljno siguran (amplituda dogadjaja, 0..1).
DEFAULT_MIN_CONFIDENCE = 0.25

# Realan opseg harmonike: od basa F2 (41) do vrha desne ruke A6 (93).
# Sve van toga je skoro sigurno sum ili harmonik, pa se sece jos u modelu.
ACCORDION_MIN_PITCH = 41  # F2
ACCORDION_MAX_PITCH = 93  # A6

# Dve note iste visine razdvojene manjom pauzom su ista, isprekidana nota.
MERGE_GAP_SEC = 0.06

# Prozor u kome trazimo "duh" harmonik i intervali na kojima se javlja:
# oktava (+12), kvintdecima (+19), dve oktave (+24) i 5. harmonik (+28).
GHOST_ONSET_WINDOW_SEC = 0.09
GHOST_INTERVALS = (12, 19, 24, 28)
GHOST_CONFIDENCE_RATIO = 0.95


class TranscriptionError(RuntimeError):
    """Transkripcija nije mogla da se izvrsi (nedostaje zavisnost/model, los ulaz)."""


@dataclass(slots=True)
class TranscriptionParams:
    """Parametri pipeline-a; svi imaju razumne podrazumevane vrednosti."""

    # Prepoznavanje nota (Task 2)
    onset_threshold: float = DEFAULT_ONSET_THRESHOLD
    frame_threshold: float = DEFAULT_FRAME_THRESHOLD
    min_note_length_ms: float = DEFAULT_MIN_NOTE_LENGTH_MS
    min_pitch: int = ACCORDION_MIN_PITCH
    max_pitch: int = ACCORDION_MAX_PITCH
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    drop_harmonic_ghosts: bool = True

    # Ritam i tonalitet (Task 3)
    grid: int = DEFAULT_GRID  # 8 = osmina, 16 = sesnaestina
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    quantize: bool = True
    snap_to_scale: bool = False  # izbaci vanlestvicne note niske pouzdanosti

    # Razdvajanje ruku (Task 4)
    hands: HandSplitParams = field(default_factory=HandSplitParams)


@dataclass(slots=True)
class RawTranscription:
    """Sirov rezultat basic-pitch faze."""

    source: Path
    notes: list[Note]  # ociscene note: filtrirane, spojene, bez harmonika-duhova
    midi: Any  # sirovi `pretty_midi.PrettyMIDI` iz basic-pitch-a, pre ciscenja
    duration_sec: float
    warnings: list[str] = field(default_factory=list)
    samples: Any = None  # dekodiran mono signal (koristi ga analiza tempa)
    sample_rate: int = 0

    def to_pretty_midi(self, tempo_bpm: float = 120.0, program: int = 21) -> Any:
        """Napravi jednostazni `PrettyMIDI` od ociscenih nota.

        `program=21` je General MIDI "Accordion". Za dvostazni izvoz (leva/desna
        ruka) koristi `notemkr.export`.
        """
        import pretty_midi

        midi = pretty_midi.PrettyMIDI(initial_tempo=float(tempo_bpm))
        instrument = pretty_midi.Instrument(program=program, name="notemkr")
        for note in self.notes:
            instrument.notes.append(
                pretty_midi.Note(
                    velocity=int(note["velocity"]),
                    pitch=int(note["pitch"]),
                    start=float(note["start"]),
                    end=float(note["end"]),
                )
            )
        midi.instruments.append(instrument)
        return midi


def _load_basic_pitch():
    """Uvezi basic-pitch i vrati `(predict, model_path)`.

    basic-pitch bira backend pri uvozu; u ovom projektu je to ONNX (`nmp.onnx`),
    jer TensorFlow namerno nije instaliran (vidi README, sekcija o instalaciji).
    """
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ImportError as exc:  # pragma: no cover - zavisi od okruzenja
        raise TranscriptionError(
            "basic-pitch nije instaliran. Instaliraj ga bez njegovih (TensorFlow) "
            "zavisnosti:\n    pip install --no-deps basic-pitch==0.4.0"
        ) from exc

    return predict, ICASSP_2022_MODEL_PATH


def _events_to_notes(note_events: list[tuple], params: TranscriptionParams) -> list[Note]:
    """basic-pitch dogadjaji `(start, end, pitch, amplitude, bends)` -> nase note."""
    notes: list[Note] = []
    for start, end, pitch, amplitude, *_ in note_events:
        confidence = float(amplitude)
        if confidence < params.min_confidence:
            continue
        if not params.min_pitch <= int(pitch) <= params.max_pitch:
            continue
        if (float(end) - float(start)) * 1000.0 < params.min_note_length_ms:
            continue
        notes.append(
            make_note(
                pitch=int(pitch),
                start=float(start),
                end=float(end),
                velocity=velocity_from_amplitude(confidence),
                confidence=round(confidence, 4),
            )
        )
    return sort_notes(notes)


def _merge_repeated(notes: list[Note], gap: float = MERGE_GAP_SEC) -> list[Note]:
    """Spoji note iste visine koje se preklapaju ili ih deli zanemarljiva pauza.

    basic-pitch ume da izdeli jedan dugi ton na vise fragmenata; u notnom zapisu
    to izgleda kao lazno ponavljanje tona.
    """
    last_by_pitch: dict[int, Note] = {}
    out: list[Note] = []

    for note in sort_notes(notes):
        previous = last_by_pitch.get(note["pitch"])
        if previous is not None and note["start"] - previous["end"] <= gap:
            previous["end"] = max(previous["end"], note["end"])
            previous["velocity"] = max(previous["velocity"], note["velocity"])
            previous["confidence"] = max(previous["confidence"], note["confidence"])
            continue
        copy = dict(note)
        last_by_pitch[note["pitch"]] = copy
        out.append(copy)

    return sort_notes(out)


def _drop_ghosts(notes: list[Note]) -> list[Note]:
    """Izbaci "duhove" — harmonike koje model prijavi kao zasebne note.

    Ton harmonike je bogat harmonicima, pa model uz pravu notu cesto prijavi i
    oktavu/kvintdecimu iznad, sa istim pocetkom i osetno manjom pouzdanoscu.
    Bez ovog koraka bi "skyline" melodija (Task 4) hvatala harmonik umesto tona.
    """
    return [
        note
        for note in notes
        if not any(
            other is not note
            and (note["pitch"] - other["pitch"]) in GHOST_INTERVALS
            and abs(other["start"] - note["start"]) <= GHOST_ONSET_WINDOW_SEC
            and note["confidence"] < other["confidence"] * GHOST_CONFIDENCE_RATIO
            for other in notes
        )
    ]


def extract_notes(
    path: str | Path,
    params: TranscriptionParams | None = None,
) -> RawTranscription:
    """Izvuci note iz audio fajla pomocu basic-pitch-a (ONNX backend).

    Args:
        path: Putanja do ulaznog audio fajla (MP3, WAV, M4A...).
        params: Parametri pragova/opsega; podrazumevano `TranscriptionParams()`.

    Returns:
        `RawTranscription` sa ociscenom listom nota i sirovim `PrettyMIDI` objektom.

    Raises:
        TranscriptionError: basic-pitch nije dostupan ili je inferencija pukla.
        AudioLoadError: ulazni fajl se ne moze dekodirati.
    """
    import librosa

    params = params or TranscriptionParams()
    src = Path(path).expanduser()
    warnings: list[str] = []

    # Dekodiramo sami (mono, 22050 Hz) da bismo rano i sa jasnom porukom otkrili
    # pokvaren fajl ili nedostatak ffmpeg-a, i da izmerimo trajanje i tisinu.
    samples, sample_rate = load_audio(src)
    duration_sec = round(len(samples) / float(sample_rate), 3)
    if is_silent(samples):
        warnings.append("Snimak je prakticno tisina — nema sta da se transkribuje.")
        return RawTranscription(src, [], None, duration_sec, warnings, samples, sample_rate)

    predict, model_path = _load_basic_pitch()
    try:
        _model_output, midi_data, note_events = predict(
            str(src),
            model_path,
            onset_threshold=params.onset_threshold,
            frame_threshold=params.frame_threshold,
            minimum_note_length=params.min_note_length_ms,
            minimum_frequency=float(librosa.midi_to_hz(params.min_pitch)),
            maximum_frequency=float(librosa.midi_to_hz(params.max_pitch)),
        )
    except Exception as exc:  # pragma: no cover - zavisi od modela/okruzenja
        raise TranscriptionError(f"basic-pitch inferencija nije uspela: {exc}") from exc

    notes = _events_to_notes(list(note_events), params)
    notes = _merge_repeated(notes)
    if params.drop_harmonic_ghosts:
        notes = _drop_ghosts(notes)

    if not notes:
        warnings.append(
            "Nijedna nota nije prepoznata — probaj nizi onset/frame prag "
            "ili kvalitetniji snimak."
        )

    return RawTranscription(
        source=src,
        notes=notes,
        midi=midi_data,
        duration_sec=duration_sec,
        warnings=warnings,
        samples=samples,
        sample_rate=sample_rate,
    )


def transcribe_file(path: str | Path, params: TranscriptionParams | None = None) -> dict[str, Any]:
    """Transkribuj audio fajl u strukturiran opis nota.

    Args:
        path: Putanja do ulaznog audio fajla (npr. MP3).
        params: Opcioni parametri prepoznavanja nota.

    Returns:
        Rezultat-mapa fiksne seme:

        {
            "source": str,             # putanja ulaznog fajla
            "status": str,             # "ok" | "error"
            "duration_sec": float,     # trajanje audia
            "tempo_bpm": float|None,   # procenjeni tempo
            "key": str|None,           # procenjeni tonalitet, npr. "G major"
            "time_signature": str,     # taktomer, podrazumevano "4/4"
            "right_hand": [Note],      # note desne ruke (melodija)
            "left_hand": [Note],       # note leve ruke (bas/akordi)
            "warnings": [str, ...],    # poruke za korisnika
        }
    """
    params = params or TranscriptionParams()
    source = str(Path(path))
    try:
        raw = extract_notes(path, params)
    except Exception as exc:
        return _empty_result(source, params, warnings=[str(exc)], status="error")

    warnings = list(raw.warnings)
    if not raw.notes:
        return _empty_result(source, params, warnings, duration_sec=raw.duration_sec)

    # Tempo i mreza doba iz istog signala koji je vec dekodiran za transkripciju.
    rhythm = analyze_rhythm(raw.samples, raw.sample_rate, params.beats_per_bar)
    warnings.extend(rhythm.warnings)

    notes = quantize_notes(raw.notes, rhythm, params.grid) if params.quantize else raw.notes

    key = estimate_key(notes)
    if key is not None and params.snap_to_scale:
        notes = snap_to_scale(notes, key)

    right_hand, left_hand = split_hands(notes, params.hands)
    if not left_hand:
        warnings.append("Nije prepoznata leva ruka — sve note su u opsegu desne.")
    if not right_hand:
        warnings.append("Nije prepoznata melodija u opsegu desne ruke.")

    return {
        "source": source,
        "status": "ok",
        "duration_sec": raw.duration_sec,
        "tempo_bpm": rhythm.tempo_bpm,
        "key": key.name if key else None,
        "time_signature": f"{params.beats_per_bar}/4",
        "right_hand": right_hand,
        "left_hand": left_hand,
        "warnings": warnings,
    }


def _empty_result(
    source: str,
    params: TranscriptionParams,
    warnings: list[str],
    status: str = "ok",
    duration_sec: float = 0.0,
) -> dict[str, Any]:
    """Rezultat-mapa bez nota (greska ili tisina) — ista sema kao i uspesan prolaz."""
    return {
        "source": source,
        "status": status,
        "duration_sec": duration_sec,
        "tempo_bpm": None,
        "key": None,
        "time_signature": f"{params.beats_per_bar}/4",
        "right_hand": [],
        "left_hand": [],
        "warnings": list(warnings),
    }
