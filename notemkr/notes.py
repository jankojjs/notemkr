"""Zajednicki "ugovor" za notu — jedan format kroz ceo pipeline.

Sve faze (transkripcija -> kvantizacija -> razdvajanje ruku -> izvoz) razmenjuju
liste obicnih `dict`-ova, tako da je rezultat direktno JSON-serializabilan (bitno
za web sloj) i lak za testiranje.

Nota:
    {
        "pitch": int,          # MIDI visina (60 = C4)
        "start": float,        # pocetak u sekundama
        "end": float,          # kraj u sekundama
        "velocity": int,       # 1..127
        "confidence": float,   # 0..1, pouzdanost modela
    }

Kasnije faze dodaju polja, ne menjaju postojeca:
    "start_beat" / "duration_beats"  (kvantizacija, Task 3)
    "hand" / "chord"                 (razdvajanje ruku, Task 4)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

Note = dict[str, Any]

# Polja koja svaka nota ima od trenutka transkripcije.
BASE_KEYS = ("pitch", "start", "end", "velocity", "confidence")

PITCH_CLASS_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def make_note(
    pitch: int,
    start: float,
    end: float,
    velocity: int = 80,
    confidence: float = 1.0,
    **extra: Any,
) -> Note:
    """Napravi notu u standardnom formatu (uz opciona dodatna polja)."""
    note: Note = {
        "pitch": int(pitch),
        "start": float(start),
        "end": float(end),
        "velocity": max(1, min(127, int(velocity))),
        "confidence": float(confidence),
    }
    note.update(extra)
    return note


def duration(note: Note) -> float:
    """Trajanje note u sekundama."""
    return float(note["end"]) - float(note["start"])


def sort_notes(notes: Iterable[Note]) -> list[Note]:
    """Note poredjane po vremenu pa po visini (deterministican redosled)."""
    return sorted(notes, key=lambda n: (float(n["start"]), int(n["pitch"])))


def pitch_name(pitch: int) -> str:
    """MIDI visina -> ime tona sa oktavom, npr. 60 -> 'C4'."""
    return f"{PITCH_CLASS_NAMES[int(pitch) % 12]}{int(pitch) // 12 - 1}"


def velocity_from_amplitude(amplitude: float) -> int:
    """Amplituda basic-pitch-a (0..1) -> MIDI velocity (1..127)."""
    return max(1, min(127, round(float(amplitude) * 126.0) + 1))
