"""Izvoz rezultata: MIDI i MusicXML (kasnije i PDF).

Koristi pretty_midi/mido za MIDI i music21 za MusicXML. Teske zavisnosti se uvoze
lenjivo unutar funkcija. Stub — implementacija dolazi u Tasku 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_midi(result: dict[str, Any], out_path: str | Path) -> Path:
    """Izvezi rezultat transkripcije u MIDI fajl.

    Stub: implementacija dolazi u Tasku 6.
    """
    raise NotImplementedError("export_midi: implementacija dolazi u Tasku 6 (izvoz).")


def export_musicxml(result: dict[str, Any], out_path: str | Path) -> Path:
    """Izvezi rezultat transkripcije u MusicXML fajl.

    Stub: implementacija dolazi u Tasku 6.
    """
    raise NotImplementedError("export_musicxml: implementacija dolazi u Tasku 6 (izvoz).")
