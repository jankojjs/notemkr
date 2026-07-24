"""Razdvajanje leve i desne ruke.

Heuristika (kasnije): melodija/desna ruka su vise note i glavni glas, dok su bas i
akordi (leva ruka) nize note. Za harmoniku je ovo kljucni korak jer se leva i desna
ruka sviraju odvojeno. Stub — implementacija dolazi u Tasku 5.
"""

from __future__ import annotations

from typing import Any

# Podrazumevana granica (MIDI pitch) ispod koje note idu u levu ruku.
# C3 = 48. Ovo je samo pocetna heuristika i bice zamenjeno pametnijom logikom.
DEFAULT_SPLIT_PITCH = 48


def split_hands(
    notes: list[dict[str, Any]], split_pitch: int = DEFAULT_SPLIT_PITCH
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Razdvoji note na (desna_ruka, leva_ruka).

    Stub: vraca dve prazne liste. Implementacija dolazi u Tasku 5.
    """
    return [], []
