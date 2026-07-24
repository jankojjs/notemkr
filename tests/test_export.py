"""Testovi Taska 5: izvoz MIDI + MusicXML (+ PDF).

Acceptance:
- `.musicxml` se otvara sa dva sistema i ispravnim kljucevima,
- `.mid` reprodukuje razdvojene ruke.
"""

from __future__ import annotations

import pytest
from conftest import requires_basic_pitch, requires_sample

from notemkr.export import (
    LEFT_HAND_NAME,
    RIGHT_HAND_NAME,
    build_score,
    export_all,
    export_midi,
    export_musicxml,
    export_pdf,
    find_musescore,
)
from notemkr.notes import make_note

# Mali, rucno napravljen rezultat — testovi partiture ne moraju da cekaju model.
SIMPLE_RESULT = {
    "source": "samples/pesma.mp3",
    "status": "ok",
    "duration_sec": 4.0,
    "tempo_bpm": 100.0,
    "key": "G major",
    "time_signature": "4/4",
    "right_hand": [
        make_note(67, 0.0, 0.6, start_beat=0.0, duration_beats=1.0),
        make_note(71, 0.6, 1.2, start_beat=1.0, duration_beats=1.0),
        make_note(74, 1.2, 2.4, start_beat=2.0, duration_beats=2.0),
    ],
    "left_hand": [
        make_note(43, 0.0, 0.6, start_beat=0.0, duration_beats=1.0, role="bass"),
        make_note(55, 0.6, 1.2, start_beat=1.0, duration_beats=1.0, role="chord"),
        make_note(59, 0.6, 1.2, start_beat=1.0, duration_beats=1.0, role="chord"),
        make_note(62, 0.6, 1.2, start_beat=1.0, duration_beats=1.0, role="chord"),
    ],
    "warnings": [],
}


# --- partitura -----------------------------------------------------------------------


def test_score_ima_dva_sistema_sa_ispravnim_kljucevima():
    from music21 import clef

    score = build_score(SIMPLE_RESULT)
    parts = list(score.parts)

    assert len(parts) == 2
    assert parts[0].partName == RIGHT_HAND_NAME
    assert parts[1].partName == LEFT_HAND_NAME
    assert isinstance(parts[0].recurse().getElementsByClass(clef.Clef)[0], clef.TrebleClef)
    assert isinstance(parts[1].recurse().getElementsByClass(clef.Clef)[0], clef.BassClef)


def test_score_nosi_tempo_taktomer_i_tonalitet():
    from music21 import key, meter, tempo

    score = build_score(SIMPLE_RESULT)
    parts = list(score.parts)

    marks = parts[0].recurse().getElementsByClass(tempo.MetronomeMark)
    assert marks and marks[0].number == pytest.approx(100.0)

    signatures = parts[0].recurse().getElementsByClass(meter.TimeSignature)
    assert signatures[0].ratioString == "4/4"

    for part in parts:
        found = part.recurse().getElementsByClass(key.Key)
        assert found and found[0].sharps == 1, "G-dur ima jednu povisilicu"


def test_score_spaja_istovremene_note_u_akord():
    from music21 import chord

    score = build_score(SIMPLE_RESULT)
    chords = list(score.parts[1].recurse().getElementsByClass(chord.Chord))

    assert len(chords) == 1
    assert sorted(pitch.midi for pitch in chords[0].pitches) == [55, 59, 62]


def test_tonalitet_koristi_citljive_predznake():
    from music21 import key

    # A# major bi imao 10 povisilica; ocekujemo enharmonijski B-dur (2 snizilice).
    score = build_score({**SIMPLE_RESULT, "key": "A# major"})
    signature = score.parts[0].recurse().getElementsByClass(key.Key)[0]

    assert signature.sharps == -2


def test_score_bez_tonaliteta_ne_puca():
    score = build_score({**SIMPLE_RESULT, "key": None, "tempo_bpm": None})

    assert len(list(score.parts)) == 2


# --- fajlovi -------------------------------------------------------------------------


def test_export_musicxml_pise_dva_parta(tmp_path):
    from music21 import converter

    out = export_musicxml(SIMPLE_RESULT, tmp_path / "pesma.musicxml")

    assert out.is_file() and out.stat().st_size > 0
    xml = out.read_text(encoding="utf-8")
    assert "<score-partwise" in xml
    assert xml.count("<part-name>") == 2

    # Najbolja provera "da li se otvara": procitati fajl nazad.
    reloaded = converter.parse(str(out))
    assert len(list(reloaded.parts)) == 2


def test_export_midi_pise_dve_staze(tmp_path):
    import pretty_midi

    out = export_midi(SIMPLE_RESULT, tmp_path / "pesma.mid")
    midi = pretty_midi.PrettyMIDI(str(out))

    assert [instrument.name for instrument in midi.instruments] == [
        RIGHT_HAND_NAME,
        LEFT_HAND_NAME,
    ]
    assert [len(instrument.notes) for instrument in midi.instruments] == [3, 4]


def test_export_pravi_folder_ako_ne_postoji(tmp_path):
    out = export_midi(SIMPLE_RESULT, tmp_path / "novi" / "pod" / "pesma.mid")

    assert out.is_file()


def test_export_all_imenuje_fajlove_po_snimku(tmp_path):
    files = export_all(SIMPLE_RESULT, out_dir=tmp_path, with_pdf=False)

    assert files["midi"].name == "pesma.mid"
    assert files["musicxml"].name == "pesma.musicxml"
    assert files["pdf"] is None
    assert all(path.is_file() for path in (files["midi"], files["musicxml"]))


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore CLI nije instaliran")
def test_export_pdf_kada_ima_musescore(tmp_path):
    musicxml = export_musicxml(SIMPLE_RESULT, tmp_path / "pesma.musicxml")

    pdf = export_pdf(musicxml, tmp_path / "pesma.pdf")

    assert pdf is not None and pdf.is_file()


def test_export_pdf_se_preskace_bez_musescore(tmp_path, monkeypatch):
    """PDF je opcion korak — bez MuseScore-a se vraca None, bez greske."""
    monkeypatch.setattr("notemkr.export.find_musescore", lambda: None)

    assert export_pdf(tmp_path / "nema.musicxml", tmp_path / "pesma.pdf") is None


# --- integracija ---------------------------------------------------------------------


@requires_basic_pitch
@requires_sample
def test_izvoz_celog_pipeline_a(result, tmp_path):
    from music21 import clef, converter

    files = export_all(result, out_dir=tmp_path, with_pdf=False)
    score = converter.parse(str(files["musicxml"]))
    parts = list(score.parts)

    assert len(parts) == 2
    assert isinstance(parts[0].recurse().getElementsByClass(clef.Clef)[0], clef.TrebleClef)
    assert isinstance(parts[1].recurse().getElementsByClass(clef.Clef)[0], clef.BassClef)
    assert len(parts[0].recurse().notes) > 0
    assert len(parts[1].recurse().notes) > 0
    assert files["midi"].name == "melodija-test.mid"


@requires_basic_pitch
@requires_sample
def test_cli_ispisuje_rezime_i_pravi_fajlove(sample_mp3, tmp_path, capsys):
    from notemkr.cli import main

    exit_code = main([str(sample_mp3), "-o", str(tmp_path), "--no-pdf"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "G major" in output
    assert (tmp_path / "melodija-test.mid").is_file()
    assert (tmp_path / "melodija-test.musicxml").is_file()


def test_cli_vraca_gresku_za_nepostojeci_fajl(tmp_path, capsys):
    from notemkr.cli import main

    exit_code = main([str(tmp_path / "nema.mp3"), "-o", str(tmp_path)])

    assert exit_code == 1
    assert "greska" in capsys.readouterr().err
