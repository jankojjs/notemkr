"""Tempo/takt, kvantizacija ritma i procena tonaliteta.

Sirov izlaz basic-pitch-a ima "razmazane" pocetke (npr. 0.499 s, 0.511 s) i
trajanja koja ne odgovaraju nijednoj notnoj vrednosti. Ovaj modul:

1. `analyze_rhythm` — librosa beat tracking -> BPM i mreza doba,
2. `quantize_notes` — poravnanje pocetaka i trajanja na podelu (1/8, 1/16...),
3. `estimate_key` — Krumhansl-Schmuckler procena tonaliteta iz nota,
4. `snap_to_scale` — opciono izbacivanje ocigledno pogresnih (vanlestvicnih) nota.

Kvantizovane note dobijaju dodatna polja `start_beat` i `duration_beats` (u
dobama, gde je doba cetvrtina), dok `start`/`end` u sekundama ostaju poravnati sa
istom mrezom — tako i MIDI reprodukcija i notni zapis vide isti ritam.

Teske zavisnosti (librosa, numpy) se uvoze lenjivo unutar funkcija.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from .notes import PITCH_CLASS_NAMES, Note, sort_notes

# Podrazumevana podela mreze: 8 = osmina, 16 = sesnaestina.
DEFAULT_GRID = 8
DEFAULT_BEATS_PER_BAR = 4
DEFAULT_TEMPO_BPM = 120.0

# Ako librosa nadje manje od ovoliko doba, procena tempa nije pouzdana.
MIN_RELIABLE_BEATS = 4

# Beat tracker cesto promasi za oktavu (60 umesto 120 BPM i slicno). Tempo se zato
# udvostrucuje/prepolovljava dok ne udje u uobicajen opseg — mreza doba se pri tome
# gusti odnosno prorednjuje, pa ritam ostaje isti, samo se drugacije zapisuje.
TEMPO_RANGE = (70.0, 180.0)

# Krumhansl-Schmuckler profili (Krumhansl 1990) — tezine tonova u dur/mol lestvici.
KRUMHANSL_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
KRUMHANSL_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

MAJOR_SCALE_STEPS = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE_STEPS = (0, 2, 3, 5, 7, 8, 10)  # prirodni mol (+ 11 kao vodica, vidi nize)


@dataclass(slots=True)
class RhythmAnalysis:
    """Ritmicki okvir snimka: tempo, mreza doba i taktomer."""

    tempo_bpm: float
    beat_times: list[float] = field(default_factory=list)
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_tempo(
        cls,
        tempo_bpm: float = DEFAULT_TEMPO_BPM,
        beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    ) -> RhythmAnalysis:
        """Ravnomerna mreza iz zadatog tempa (bez beat trackinga)."""
        return cls(tempo_bpm=float(tempo_bpm), beat_times=[], beats_per_bar=beats_per_bar)

    @property
    def beat_period(self) -> float:
        """Trajanje jedne dobe u sekundama."""
        return 60.0 / max(1e-6, self.tempo_bpm)


@dataclass(slots=True)
class KeyEstimate:
    """Procenjeni tonalitet."""

    tonic: str  # npr. "G", "F#"
    mode: str  # "major" | "minor"
    correlation: float  # 0..1, koliko profil odgovara (mera pouzdanosti)

    @property
    def name(self) -> str:
        """Ime tonaliteta u obliku koji razume i music21, npr. 'G major'."""
        return f"{self.tonic} {self.mode}"

    def scale_pitch_classes(self) -> set[int]:
        """Tonovi lestvice kao klase visina (0-11)."""
        tonic_pc = PITCH_CLASS_NAMES.index(self.tonic)
        steps = MAJOR_SCALE_STEPS if self.mode == "major" else MINOR_SCALE_STEPS
        pcs = {(tonic_pc + step) % 12 for step in steps}
        if self.mode == "minor":
            pcs.add((tonic_pc + 11) % 12)  # harmonski mol: povisena vodica
        return pcs


# --- tempo / mreza doba --------------------------------------------------------------


def analyze_rhythm(
    samples: Any,
    sample_rate: int,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
) -> RhythmAnalysis:
    """Proceni tempo (BPM) i mrezu doba iz audio signala (librosa beat tracking)."""
    import librosa
    import numpy as np

    warnings: list[str] = []
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=samples, sr=sample_rate, units="frames")
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)
    except Exception as exc:  # pragma: no cover - zavisi od signala
        warnings.append(f"Beat tracking nije uspeo ({exc}); koristim {DEFAULT_TEMPO_BPM:.0f} BPM.")
        return RhythmAnalysis(DEFAULT_TEMPO_BPM, [], beats_per_bar, warnings)

    tempo_bpm = float(np.atleast_1d(tempo)[0])
    beats = [float(t) for t in np.atleast_1d(beat_times)]

    if len(beats) < MIN_RELIABLE_BEATS or tempo_bpm <= 0:
        warnings.append(
            "Tempo nije pouzdano prepoznat (prekratak ili neritmican snimak); "
            f"koristim {DEFAULT_TEMPO_BPM:.0f} BPM."
        )
        return RhythmAnalysis(DEFAULT_TEMPO_BPM, [], beats_per_bar, warnings)

    tempo_bpm, beats = normalize_tempo_octave(tempo_bpm, beats)
    return RhythmAnalysis(round(tempo_bpm, 2), beats, beats_per_bar, warnings)


def normalize_tempo_octave(
    tempo_bpm: float,
    beat_times: list[float],
    tempo_range: tuple[float, float] = TEMPO_RANGE,
) -> tuple[float, list[float]]:
    """Prebaci tempo u uobicajen opseg udvostrucavanjem/prepolovljavanjem.

    Beat tracker ume da zakljuca duplo sporiji (ili brzi) puls od onog koji bi
    muzicar zapisao. Mreza doba se menja zajedno sa tempom: pri udvostrucavanju se
    ubacuju medjudobe, pri prepolovljavanju se izbacuje svaka druga doba.
    """
    low, high = tempo_range
    beats = list(beat_times)

    while tempo_bpm < low and tempo_bpm > 0:
        tempo_bpm *= 2.0
        beats = _interleave_midpoints(beats)
    while tempo_bpm > high:
        tempo_bpm /= 2.0
        beats = beats[::2]

    return tempo_bpm, beats


def _interleave_midpoints(beats: list[float]) -> list[float]:
    """Ubaci sredinu izmedju svake dve susedne dobe (dvostruko gusca mreza)."""
    if len(beats) < 2:
        return beats
    dense: list[float] = []
    for current, following in pairwise(beats):
        dense.append(current)
        dense.append((current + following) / 2.0)
    dense.append(beats[-1])
    return dense


def _beat_grid(rhythm: RhythmAnalysis, until: float) -> tuple[list[float], list[float]]:
    """Mreza doba prosirena tako da pokriva ceo snimak: `(vremena, pozicije_doba)`.

    librosa vraca doba samo tamo gde ih je detektovala; note pre prve i posle
    poslednje dobe se mapiraju ekstrapolacijom sa medijana razmaka.
    """
    import numpy as np

    if len(rhythm.beat_times) < 2:
        period = rhythm.beat_period
        count = int(max(2.0, until / period)) + 2
        return [i * period for i in range(count)], [float(i) for i in range(count)]

    times = list(rhythm.beat_times)
    period = float(np.median(np.diff(times))) or rhythm.beat_period
    positions = [float(i) for i in range(len(times))]

    while times[0] > 0.0:
        times.insert(0, times[0] - period)
        positions.insert(0, positions[0] - 1.0)
    while times[-1] < until + period:
        times.append(times[-1] + period)
        positions.append(positions[-1] + 1.0)

    return times, positions


# --- kvantizacija --------------------------------------------------------------------


def quantize_notes(
    notes: list[Note],
    rhythm: RhythmAnalysis | None = None,
    grid: int = DEFAULT_GRID,
) -> list[Note]:
    """Poravnaj pocetke i trajanja nota na ritmicku mrezu.

    Args:
        notes: Note sa `start`/`end` u sekundama.
        rhythm: Ritmicki okvir; podrazumevano ravnomernih 120 BPM.
        grid: Najsitnija podela — 8 za osminu, 16 za sesnaestinu, 4 za cetvrtinu.

    Returns:
        Nove note (ulaz se ne menja) sa poravnatim `start`/`end` i dodatim
        `start_beat` / `duration_beats`. Beat 0 je pocetak prvog takta.
    """
    import numpy as np

    if not notes:
        return []

    rhythm = rhythm or RhythmAnalysis.from_tempo()
    step_beats = 4.0 / max(1, grid)  # u 4/4 je doba cetvrtina

    last_end = max(float(n["end"]) for n in notes)
    times, positions = _beat_grid(rhythm, last_end)

    starts = np.interp([float(n["start"]) for n in notes], times, positions)
    ends = np.interp([float(n["end"]) for n in notes], times, positions)

    snapped_starts = np.round(starts / step_beats) * step_beats
    snapped_ends = np.round(ends / step_beats) * step_beats
    # Nijedna nota ne sme da nestane: minimum je jedan korak mreze.
    snapped_ends = np.maximum(snapped_ends, snapped_starts + step_beats)

    # Prva nota je pocetak prvog takta: beat tracker daje mrezu bez podatka o tome
    # gde je teska doba, pa bi svaka druga nula ostavila izmisljenu pauzu na pocetku.
    origin = float(snapped_starts.min())

    out: list[Note] = []
    for note, start_beat, end_beat in zip(notes, snapped_starts, snapped_ends, strict=True):
        quantized = dict(note)
        quantized["start"] = round(float(np.interp(start_beat, positions, times)), 4)
        quantized["end"] = round(float(np.interp(end_beat, positions, times)), 4)
        quantized["start_beat"] = round(float(start_beat) - origin, 4)
        quantized["duration_beats"] = round(float(end_beat - start_beat), 4)
        out.append(quantized)

    return sort_notes(out)


# --- tonalitet -----------------------------------------------------------------------


def pitch_class_weights(notes: list[Note]) -> list[float]:
    """Histogram klasa visina, tezinski po trajanju i pouzdanosti note."""
    weights = [0.0] * 12
    for note in notes:
        duration = max(0.0, float(note["end"]) - float(note["start"]))
        weights[int(note["pitch"]) % 12] += duration * float(note.get("confidence", 1.0))
    return weights


def _correlation(profile: tuple[float, ...], weights: list[float]) -> float:
    """Pearsonova korelacija profila lestvice i izmerenog histograma."""
    import numpy as np

    a = np.asarray(profile, dtype=float)
    b = np.asarray(weights, dtype=float)
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def estimate_key(notes: list[Note]) -> KeyEstimate | None:
    """Proceni tonalitet Krumhansl-Schmuckler metodom.

    Histogram klasa visina (tezinski po trajanju) se uporedjuje sa dur i mol
    profilom u svih 12 transpozicija; bira se najbolja korelacija.

    Returns:
        `KeyEstimate` ili `None` ako nema dovoljno materijala za procenu.
    """
    weights = pitch_class_weights(notes)
    if sum(weights) <= 0:
        return None

    best: KeyEstimate | None = None
    for tonic_pc in range(12):
        rotated = weights[tonic_pc:] + weights[:tonic_pc]
        for mode, profile in (("major", KRUMHANSL_MAJOR), ("minor", KRUMHANSL_MINOR)):
            score = _correlation(profile, rotated)
            if best is None or score > best.correlation:
                best = KeyEstimate(PITCH_CLASS_NAMES[tonic_pc], mode, round(score, 4))

    return best


def snap_to_scale(
    notes: list[Note],
    key: KeyEstimate,
    max_confidence: float = 0.5,
) -> list[Note]:
    """Izbaci vanlestvicne note u koje model nije siguran ("snap na lestvicu").

    Note van lestvice mogu biti prave (hromatika, modulacija), pa se izbacuju samo
    one sa niskom pouzdanoscu — tipicni artefakti transkripcije.
    """
    allowed = key.scale_pitch_classes()
    return [
        note
        for note in notes
        if int(note["pitch"]) % 12 in allowed
        or float(note.get("confidence", 1.0)) >= max_confidence
    ]
