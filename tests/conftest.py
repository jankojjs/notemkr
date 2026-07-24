"""Zajednicke fixture-e za testove."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_MP3 = REPO_ROOT / "samples" / "melodija-test.mp3"


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover
        return False


# Integracioni testovi zahtevaju model i test snimak; bez njih se preskacu, da
# `pytest` prolazi i u okruzenju gde basic-pitch nije instaliran.
requires_basic_pitch = pytest.mark.skipif(
    not _module_available("basic_pitch"),
    reason="basic-pitch nije instaliran (pip install --no-deps basic-pitch==0.4.0)",
)

requires_sample = pytest.mark.skipif(
    not SAMPLE_MP3.is_file(),
    reason=f"nedostaje test snimak: {SAMPLE_MP3}",
)

# Testovi web sloja traze fastapi + httpx (TestClient) i python-multipart za upload.
requires_web_stack = pytest.mark.skipif(
    not all(_module_available(name) for name in ("fastapi", "httpx", "multipart")),
    reason='web stack nije instaliran (pip install -e ".[dev]")',
)


@pytest.fixture(scope="session")
def sample_mp3() -> Path:
    """Putanja do kratkog test MP3-a (generise ga `samples/make_sample.py`)."""
    return SAMPLE_MP3


@pytest.fixture(scope="session")
def transcription(sample_mp3: Path):
    """Sirova transkripcija test snimka — deli se kroz celu sesiju (inferencija je spora)."""
    from notemkr.transcribe import extract_notes

    return extract_notes(sample_mp3)


@pytest.fixture(scope="session")
def result(sample_mp3: Path) -> dict:
    """Pun rezultat `transcribe_file` za test snimak (jednom po sesiji)."""
    from notemkr import transcribe_file

    return transcribe_file(sample_mp3)
