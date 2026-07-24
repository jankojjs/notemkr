"""Dekodiranje i priprema audia.

Runtime zavisnost: `ffmpeg` mora biti dostupan u PATH-u za dekodiranje MP3/M4A i
slicnih formata (librosa ga koristi preko audioread kada soundfile ne podrzava format).

Sve funkcije rade cross-platform (koriste `pathlib`, bez OS-specificnih putanja).
Teske zavisnosti (librosa, numpy) se uvoze lenjivo unutar funkcija, tako da
`import notemkr` ostaje trenutan.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

# Ciljni sample rate za transkripciju (basic-pitch interno radi na 22050 Hz).
TARGET_SAMPLE_RATE = 22050

# Ispod ovog RMS-a smatramo da je snimak prakticno tisina (nema sta da se transkribuje).
SILENCE_RMS_THRESHOLD = 1e-4


class AudioLoadError(RuntimeError):
    """Ulazni audio se ne moze procitati (nema fajla, nema ffmpeg-a, los format)."""


def ffmpeg_available() -> bool:
    """Da li je `ffmpeg` u PATH-u (potreban za MP3/M4A dekodiranje)."""
    return shutil.which("ffmpeg") is not None


def load_audio(path: str | Path, sample_rate: int = TARGET_SAMPLE_RATE) -> tuple[Any, int]:
    """Ucitaj audio fajl kao mono numpy niz na zadatom sample rate-u.

    Args:
        path: Putanja do audio fajla (MP3, WAV, M4A, FLAC...).
        sample_rate: Ciljni sample rate; podrazumevano 22050 Hz (basic-pitch native).

    Returns:
        Tuple `(samples, sample_rate)`, gde je `samples` 1-D `float32` numpy niz u
        opsegu [-1, 1], vec svenut na mono i resamplovan.

    Raises:
        AudioLoadError: fajl ne postoji, prazan je, ili ga dekoder ne moze otvoriti.
    """
    import librosa

    src = Path(path).expanduser()
    if not src.is_file():
        raise AudioLoadError(f"Audio fajl ne postoji: {src}")

    try:
        samples, sr = librosa.load(str(src), sr=sample_rate, mono=True)
    except Exception as exc:  # librosa/audioread dizu razne tipove gresaka
        hint = "" if ffmpeg_available() else " (savet: `ffmpeg` nije u PATH-u — instaliraj ga)"
        raise AudioLoadError(f"Ne mogu da dekodiram audio: {src}{hint}") from exc

    if samples.size == 0:
        raise AudioLoadError(f"Audio fajl je prazan (0 semplova): {src}")

    return samples, int(sr)


def audio_duration(path: str | Path) -> float:
    """Trajanje audia u sekundama.

    Prvo pokusava jeftino citanje iz zaglavlja; ako format to ne dozvoljava, pada
    nazad na punu dekodu.
    """
    import librosa

    src = Path(path).expanduser()
    try:
        return float(librosa.get_duration(path=str(src)))
    except Exception:
        samples, sr = load_audio(src)
        return float(len(samples)) / float(sr)


def is_silent(samples: Any, threshold: float = SILENCE_RMS_THRESHOLD) -> bool:
    """Da li je signal prakticno tisina (RMS ispod praga)."""
    import numpy as np

    if samples.size == 0:
        return True
    return bool(np.sqrt(np.mean(np.square(samples.astype("float64")))) < threshold)
