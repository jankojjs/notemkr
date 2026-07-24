"""Dekodiranje i priprema audia.

Runtime zavisnost: `ffmpeg` mora biti dostupan u PATH-u za dekodiranje MP3/M4A i
slicnih formata (librosa/soundfile ga koristi preko audioread na nekim platformama).

Sve funkcije rade cross-platform (koriste `pathlib`, bez OS-specificnih putanja).
Teske zavisnosti se uvoze lenjivo, unutar funkcija.
"""

from __future__ import annotations

from pathlib import Path

# Ciljni sample rate za transkripciju (basic-pitch interno radi na 22050 Hz).
TARGET_SAMPLE_RATE = 22050


def load_audio(path: str | Path, sample_rate: int = TARGET_SAMPLE_RATE):
    """Ucitaj audio fajl kao mono numpy niz na zadatom sample rate-u.

    Vraca tuple `(samples, sample_rate)`. Stub: implementacija dolazi u Tasku 2.
    """
    raise NotImplementedError("load_audio: implementacija dolazi u Tasku 2 (audio dekodiranje).")
