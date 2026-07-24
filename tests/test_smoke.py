"""Smoke test: paket se uvozi i `transcribe_file` postuje ugovor rezultat-mape.

Ugovor (`source`, `status`, `duration_sec`, `tempo_bpm`, `key`, `right_hand`,
`left_hand`, `warnings`) je stabilan kroz sve faze pipeline-a — web sloj i izvoz
racunaju na njega.
"""

from __future__ import annotations

from conftest import requires_basic_pitch, requires_sample

import notemkr
from notemkr import transcribe_file

RESULT_KEYS = (
    "source",
    "status",
    "duration_sec",
    "tempo_bpm",
    "key",
    "right_hand",
    "left_hand",
    "warnings",
)


def test_package_has_version():
    assert isinstance(notemkr.__version__, str)


def test_transcribe_file_ugovor_i_na_gresci(tmp_path):
    """Rezultat-mapa ima istu semu i kada ulaz ne moze da se procita."""
    result = transcribe_file(tmp_path / "nepostojeci.mp3")

    for key in RESULT_KEYS:
        assert key in result, f"nedostaje kljuc: {key}"

    assert result["status"] == "error"
    assert result["right_hand"] == []
    assert result["left_hand"] == []
    assert isinstance(result["warnings"], list)


@requires_basic_pitch
@requires_sample
def test_transcribe_file_ugovor_na_pravom_snimku(result):
    for key in RESULT_KEYS:
        assert key in result, f"nedostaje kljuc: {key}"

    assert result["status"] == "ok"
    assert result["duration_sec"] > 0
    assert isinstance(result["right_hand"], list)
    assert isinstance(result["left_hand"], list)
    assert isinstance(result["warnings"], list)
