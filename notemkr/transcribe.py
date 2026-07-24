"""Pipeline za transkripciju: MP3 -> note.

`transcribe_file` je glavna ulazna tacka celog alata. U ovom scaffold-u je stub koji
vraca praznu, ali validno strukturiranu rezultat-mapu, tako da se moze importovati i
pozvati bez greske (Acceptance kriterijum Taska 1).

Prave faze (audio -> basic-pitch -> kvantizacija -> razdvajanje ruku -> izvoz) se
povezuju kroz taskove 2-7. Teske zavisnosti se uvoze lenjivo unutar tih faza.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def transcribe_file(path: str | Path) -> dict[str, Any]:
    """Transkribuj audio fajl u strukturiran opis nota.

    Args:
        path: Putanja do ulaznog audio fajla (npr. MP3).

    Returns:
        Rezultat-mapa sa fiksnom semom. U ovom scaffold-u su liste nota prazne
        (stub), ali struktura odgovara onome sto ce kasnije faze popunjavati:

        {
            "source": str,          # apsolutna putanja ulaznog fajla
            "status": "stub",       # kasnije: "ok" / "error"
            "duration_sec": float,  # trajanje audia (0.0 u stubu)
            "tempo_bpm": None,      # procenjeni tempo (kasnije)
            "key": None,            # procenjeni tonalitet (kasnije)
            "right_hand": [],       # note desne ruke (melodija)
            "left_hand": [],        # note leve ruke (bas/akordi)
            "warnings": [str, ...], # poruke za korisnika
        }

    Napomena: ova funkcija namerno NE uvozi teske zavisnosti niti cita fajl, tako da
    je uvoz i poziv trenutan i bez sporednih efekata.
    """
    source = str(Path(path))
    return {
        "source": source,
        "status": "stub",
        "duration_sec": 0.0,
        "tempo_bpm": None,
        "key": None,
        "right_hand": [],
        "left_hand": [],
        "warnings": ["Pipeline jos nije implementiran (scaffold stub, Task 1)."],
    }
