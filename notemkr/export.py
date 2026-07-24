"""Izvoz rezultata: MIDI (dve staze) i MusicXML (kasnije i PDF).

Koristi pretty_midi za MIDI i music21 za MusicXML. Teske zavisnosti se uvoze
lenjivo unutar funkcija.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# General MIDI programi: 21 = Accordion, 23 = Tango Accordion (leva ruka/bas).
RIGHT_HAND_PROGRAM = 21
LEFT_HAND_PROGRAM = 23

RIGHT_HAND_NAME = "Desna ruka (melodija)"
LEFT_HAND_NAME = "Leva ruka (bas/akordi)"


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

    target = Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(target))
    return target


def export_musicxml(result: dict[str, Any], out_path: str | Path) -> Path:
    """Izvezi rezultat transkripcije u MusicXML fajl.

    Stub: implementacija dolazi u Tasku 5 (partitura sa dva sistema).
    """
    raise NotImplementedError("export_musicxml: implementacija dolazi u Tasku 5 (izvoz).")
