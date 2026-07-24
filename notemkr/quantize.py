"""Kvantizacija ritma i procena tonaliteta/tempa.

Poravnava sirove note (pocetak/trajanje u sekundama) na muzicku resetku (beat/takt)
i procenjuje tempo i tonalitet. Teske zavisnosti (music21, pretty_midi) se uvoze
lenjivo unutar funkcija. Stub — implementacija dolazi u Tasku 4.
"""

from __future__ import annotations

from typing import Any


def quantize_notes(notes: list[dict[str, Any]], tempo_bpm: float | None = None) -> list[dict[str, Any]]:
    """Poravnaj note na muzicku resetku prema (procenjenom) tempu.

    Stub: vraca note nepromenjene. Implementacija dolazi u Tasku 4.
    """
    return list(notes)
