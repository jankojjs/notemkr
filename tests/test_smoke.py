"""Smoke test za scaffold: paket se uvozi i pipeline stub se poziva bez greske.

Odgovara Acceptance kriterijumu Taska 1.
"""

from __future__ import annotations

import notemkr
from notemkr import transcribe_file


def test_package_has_version():
    assert isinstance(notemkr.__version__, str)


def test_transcribe_file_stub_shape():
    result = transcribe_file("samples/primer.mp3")

    assert isinstance(result, dict)
    # Ocekivani kljucevi u rezultat-mapi.
    for key in (
        "source",
        "status",
        "duration_sec",
        "tempo_bpm",
        "key",
        "right_hand",
        "left_hand",
        "warnings",
    ):
        assert key in result, f"nedostaje kljuc: {key}"

    assert result["status"] == "stub"
    assert result["right_hand"] == []
    assert result["left_hand"] == []
    assert isinstance(result["warnings"], list)
