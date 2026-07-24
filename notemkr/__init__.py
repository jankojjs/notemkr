"""notemkr — MP3 -> notni zapis za harmoniku (leva + desna ruka).

Javni API paketa:

    from notemkr import transcribe_file, export_all

    result = transcribe_file("pesma.mp3")
    files = export_all(result)          # .mid + .musicxml (+ .pdf)

Uvoz paketa je namerno lagan: teske zavisnosti (basic-pitch, librosa, music21)
se uvoze tek unutar funkcija koje ih zaista koriste.
"""

from __future__ import annotations

from .export import export_all, export_midi, export_musicxml
from .split_hands import HandSplitParams
from .transcribe import TranscriptionParams, transcribe_file

__all__ = [
    "HandSplitParams",
    "TranscriptionParams",
    "__version__",
    "export_all",
    "export_midi",
    "export_musicxml",
    "transcribe_file",
]

__version__ = "0.1.0"
