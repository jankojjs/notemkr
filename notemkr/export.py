"""Izvoz rezultata: MIDI (dve staze), MusicXML (dva sistema) i opciono PDF.

Koristi pretty_midi za MIDI i music21 za partituru. Partitura ima dva party —
gornji sa violinskim kljucem (desna ruka, melodija) i donji sa bas kljucem (leva
ruka, bas i akordi) — i nosi tempo, taktomer i tonalitet iz analize.

MusicXML otvaraju i Sibelius i MuseScore; PDF se pravi samo ako je MuseScore CLI
dostupan (u suprotnom se korak preskace, bez greske).

Teske zavisnosti (pretty_midi, music21) se uvoze lenjivo unutar funkcija.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .notes import PITCH_CLASS_NAMES, Note
from .split_hands import group_simultaneous

# General MIDI programi: 21 = Accordion, 23 = Tango Accordion (leva ruka/bas).
RIGHT_HAND_PROGRAM = 21
LEFT_HAND_PROGRAM = 23

RIGHT_HAND_NAME = "Desna ruka (melodija)"
LEFT_HAND_NAME = "Leva ruka (bas/akordi)"

# Uobicajeni nazivi tonaliteta: dur do 6 povisilica, dalje snizilice ('-' je bemol
# u music21 notaciji). Bez ovoga bi npr. tonika "A#" dala tonalitet sa 10 povisilica.
MAJOR_KEY_NAMES = ("C", "D-", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B")
MINOR_KEY_NAMES = ("C", "C#", "D", "E-", "E", "F", "F#", "G", "G#", "A", "B-", "B")

# Kandidati za MuseScore CLI (PDF je opcion korak).
MUSESCORE_COMMANDS = ("mscore", "musescore", "MuseScore4", "mscore4", "MuseScore3")
MUSESCORE_APP_PATHS = (
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
    r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
)

PDF_TIMEOUT_SEC = 120


# --- MIDI ----------------------------------------------------------------------------


def export_midi(result: dict[str, Any], out_path: str | Path) -> Path:
    """Izvezi rezultat transkripcije u dvostazni MIDI.

    Staza 1 (kanal 0) je desna ruka, staza 2 (kanal 1) leva — tako se u svakom
    sekvenceru i notacijskom programu ruke vide odvojeno.

    Args:
        result: Rezultat-mapa iz `notemkr.transcribe_file`.
        out_path: Putanja izlaznog `.mid` fajla.

    Returns:
        Putanja napisanog fajla.
    """
    import pretty_midi

    tempo = float(result.get("tempo_bpm") or 120.0)
    midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)

    for notes, program, name in (
        (result.get("right_hand") or [], RIGHT_HAND_PROGRAM, RIGHT_HAND_NAME),
        (result.get("left_hand") or [], LEFT_HAND_PROGRAM, LEFT_HAND_NAME),
    ):
        instrument = pretty_midi.Instrument(program=program, name=name)
        for note in notes:
            instrument.notes.append(
                pretty_midi.Note(
                    velocity=int(note["velocity"]),
                    pitch=int(note["pitch"]),
                    start=float(note["start"]),
                    end=float(note["end"]),
                )
            )
        midi.instruments.append(instrument)

    target = _prepare(out_path)
    midi.write(str(target))
    return target


# --- partitura (music21) -------------------------------------------------------------


def _key_signature(key_name: str | None):
    """Naziv tonaliteta ('G major') -> `music21.key.Key`, sa citljivim predznacima."""
    from music21 import key as m21key

    if not key_name:
        return None

    tonic, _, mode = key_name.partition(" ")
    mode = mode or "major"
    if tonic not in PITCH_CLASS_NAMES:
        return None

    names = MAJOR_KEY_NAMES if mode == "major" else MINOR_KEY_NAMES
    return m21key.Key(names[PITCH_CLASS_NAMES.index(tonic)], mode)


def _beat_position(note: Note) -> float:
    """Pozicija note u dobama; ako kvantizacija nije radjena, racuna se iz sekundi."""
    return float(note.get("start_beat", note["start"]))


def _beat_duration(note: Note) -> float:
    """Trajanje note u dobama (cetvrtinama)."""
    return float(note.get("duration_beats", float(note["end"]) - float(note["start"])))


def _add_notes_to_part(part: Any, notes: list[Note]) -> None:
    """Ubaci note u part; istovremene note istog trajanja postaju akord."""
    from music21 import chord as m21chord
    from music21 import note as m21note

    for group in group_simultaneous(notes):
        # Akord je samo ono sto pocinje i traje isto; ostalo ostaje zaseban ton,
        # pa music21 sam napravi glasove umesto pogresno spojenih trajanja.
        by_duration: dict[float, list[Note]] = {}
        for item in group:
            by_duration.setdefault(round(_beat_duration(item), 4), []).append(item)

        for duration_beats, members in by_duration.items():
            offset = round(_beat_position(members[0]), 4)
            quarter_length = max(0.125, duration_beats)
            velocity = max(int(item["velocity"]) for item in members)

            if len(members) == 1:
                element = m21note.Note(int(members[0]["pitch"]))
            else:
                element = m21chord.Chord([int(item["pitch"]) for item in members])
            element.quarterLength = quarter_length
            element.volume.velocity = velocity
            part.insert(offset, element)


def build_score(result: dict[str, Any], title: str | None = None) -> Any:
    """Napravi `music21.stream.Score` sa dva sistema (desna + leva ruka).

    Args:
        result: Rezultat-mapa iz `notemkr.transcribe_file`.
        title: Naslov partiture; podrazumevano naziv ulaznog fajla.

    Returns:
        `music21.stream.Score` spreman za izvoz ili dalju obradu.
    """
    from music21 import clef, instrument, metadata, meter, stream, tempo

    score = stream.Score()
    score.insert(0, metadata.Metadata())
    score.metadata.title = title or Path(str(result.get("source", "notemkr"))).stem
    score.metadata.composer = "notemkr (automatska transkripcija)"

    time_signature = str(result.get("time_signature") or "4/4")
    key_signature = _key_signature(result.get("key"))
    tempo_bpm = float(result.get("tempo_bpm") or 120.0)

    hands = (
        (result.get("right_hand") or [], clef.TrebleClef(), RIGHT_HAND_NAME, "P1"),
        (result.get("left_hand") or [], clef.BassClef(), LEFT_HAND_NAME, "P2"),
    )

    for index, (notes, hand_clef, name, part_id) in enumerate(hands):
        part = stream.Part(id=part_id)
        part.partName = name
        part.insert(0, instrument.Accordion())
        part.insert(0, hand_clef)
        part.insert(0, meter.TimeSignature(time_signature))
        if key_signature is not None:
            part.insert(0, key_signature)
        if index == 0:  # oznaka tempa stoji iznad gornjeg sistema
            part.insert(0, tempo.MetronomeMark(number=tempo_bpm))

        _add_notes_to_part(part, notes)
        score.insert(0, part)

    return score


def export_musicxml(result: dict[str, Any], out_path: str | Path) -> Path:
    """Izvezi partituru u MusicXML (otvaraju je Sibelius i MuseScore).

    Args:
        result: Rezultat-mapa iz `notemkr.transcribe_file`.
        out_path: Putanja izlaznog `.musicxml` fajla.

    Returns:
        Putanja napisanog fajla.
    """
    score = build_score(result)
    target = _prepare(out_path)
    score.write("musicxml", fp=str(target))
    return target


# --- PDF (opciono, preko MuseScore CLI) ----------------------------------------------


def find_musescore() -> str | None:
    """Nadji MuseScore CLI, ako je instaliran (inace PDF korak nema cime da radi)."""
    from_env = os.environ.get("MUSESCORE_PATH")
    if from_env and Path(from_env).is_file():
        return from_env

    for command in MUSESCORE_COMMANDS:
        found = shutil.which(command)
        if found:
            return found

    return next((path for path in MUSESCORE_APP_PATHS if Path(path).is_file()), None)


def export_pdf(musicxml_path: str | Path, out_path: str | Path) -> Path | None:
    """Napravi PDF iz MusicXML-a preko MuseScore CLI.

    Returns:
        Putanja PDF-a, ili `None` ako MuseScore nije dostupan ili nije uspeo —
        PDF je opcion korak i nikada ne obara izvoz.
    """
    musescore = find_musescore()
    if musescore is None:
        return None

    target = _prepare(out_path)
    try:
        completed = subprocess.run(
            [musescore, "-o", str(target), str(musicxml_path)],
            capture_output=True,
            timeout=PDF_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return target if completed.returncode == 0 and target.is_file() else None


# --- sve odjednom --------------------------------------------------------------------


def export_all(
    result: dict[str, Any],
    out_dir: str | Path | None = None,
    basename: str | None = None,
    with_pdf: bool = True,
) -> dict[str, Path | None]:
    """Izvezi MIDI, MusicXML i (ako moze) PDF, imenovane po ulaznom fajlu.

    Args:
        result: Rezultat-mapa iz `notemkr.transcribe_file`.
        out_dir: Izlazni folder; podrazumevano folder ulaznog snimka.
        basename: Naziv bez ekstenzije; podrazumevano naziv ulaznog snimka.
        with_pdf: Da li pokusati i PDF (preskace se ako nema MuseScore-a).

    Returns:
        `{"midi": Path, "musicxml": Path, "pdf": Path | None}`.
    """
    source = Path(str(result.get("source") or "notemkr"))
    directory = Path(out_dir) if out_dir is not None else source.parent
    stem = basename or source.stem

    midi_path = export_midi(result, directory / f"{stem}.mid")
    musicxml_path = export_musicxml(result, directory / f"{stem}.musicxml")
    pdf_path = export_pdf(musicxml_path, directory / f"{stem}.pdf") if with_pdf else None

    return {"midi": midi_path, "musicxml": musicxml_path, "pdf": pdf_path}


def _prepare(out_path: str | Path) -> Path:
    """Normalizuj izlaznu putanju i napravi folder ako ne postoji."""
    target = Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
