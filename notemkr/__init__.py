"""notemkr — MP3 -> notni zapis za harmoniku (leva + desna ruka).

Javni API paketa. Pipeline stub `transcribe_file` je namerno lagan: ne uvozi
teske zavisnosti (basic-pitch, librosa, ...) na nivou modula, tako da se paket
moze importovati i pokrenuti odmah nakon `pip install -e .`.
"""

from __future__ import annotations

from .transcribe import transcribe_file

__all__ = ["transcribe_file", "__version__"]

__version__ = "0.1.0"
