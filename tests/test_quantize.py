"""Testovi Taska 3: tempo/takt, kvantizacija i tonalitet.

Acceptance:
- note su poravnate na mrezu (nema vise "razmazanih" pocetaka),
- izlaz sadrzi BPM i tonalitet.
"""

from __future__ import annotations

import pytest
from conftest import requires_basic_pitch, requires_sample

from notemkr.notes import make_note
from notemkr.quantize import (
    RhythmAnalysis,
    analyze_rhythm,
    estimate_key,
    normalize_tempo_octave,
    quantize_notes,
    snap_to_scale,
)

# 120 BPM -> doba = 0.5 s.
TEMPO = RhythmAnalysis.from_tempo(120.0)


def _sloppy_notes() -> list:
    """Note sa "razmazanim" pocecima oko cetvrtina na 120 BPM."""
    return [
        make_note(67, 0.012, 0.476),  # ~doba 0
        make_note(69, 0.499, 0.952),  # ~doba 1
        make_note(71, 0.975, 1.881),  # ~doba 2, traje 2 dobe
        make_note(74, 1.998, 2.474),  # ~doba 4
    ]


# --- tempo ---------------------------------------------------------------------------


def test_normalize_tempo_octave_udvostrucuje_prespor_tempo():
    tempo, beats = normalize_tempo_octave(60.0, [0.0, 1.0, 2.0, 3.0])

    assert tempo == pytest.approx(120.0)
    assert beats == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0], "ubacene su medjudobe"


def test_normalize_tempo_octave_prepolovljava_prebrz_tempo():
    tempo, beats = normalize_tempo_octave(240.0, [0.0, 0.25, 0.5, 0.75, 1.0])

    assert tempo == pytest.approx(120.0)
    assert beats == [0.0, 0.5, 1.0], "svaka druga doba je izbacena"


def test_normalize_tempo_octave_ne_dira_uobicajen_tempo():
    tempo, beats = normalize_tempo_octave(96.0, [0.0, 0.625])

    assert tempo == pytest.approx(96.0)
    assert beats == [0.0, 0.625]


# --- kvantizacija --------------------------------------------------------------------


def test_quantize_poravnava_pocetke_na_mrezu():
    quantized = quantize_notes(_sloppy_notes(), TEMPO, grid=8)

    starts = [note["start_beat"] for note in quantized]
    assert starts == [0.0, 1.0, 2.0, 4.0]
    assert all(note["duration_beats"] % 0.5 == 0 for note in quantized)


def test_quantize_cuva_sekunde_u_skladu_sa_dobama():
    quantized = quantize_notes(_sloppy_notes(), TEMPO, grid=8)

    # Na 120 BPM je doba 0.5 s, pa je i vreme u sekundama na mrezi.
    assert quantized[0]["start"] == pytest.approx(0.0, abs=1e-3)
    assert quantized[1]["start"] == pytest.approx(0.5, abs=1e-3)
    assert quantized[2]["start"] == pytest.approx(1.0, abs=1e-3)
    assert quantized[2]["end"] == pytest.approx(2.0, abs=1e-3)


def test_quantize_cuva_ostala_polja_i_ne_menja_ulaz():
    notes = _sloppy_notes()
    original = [dict(note) for note in notes]

    quantized = quantize_notes(notes, TEMPO)

    assert notes == original, "ulazna lista se ne menja"
    assert all(note["pitch"] for note in quantized)
    assert all("confidence" in note and "velocity" in note for note in quantized)


def test_quantize_ne_gubi_kratke_note():
    notes = [make_note(60, 0.50, 0.53)]  # kraca od jednog koraka mreze

    quantized = quantize_notes(notes, TEMPO, grid=8)

    assert len(quantized) == 1
    assert quantized[0]["duration_beats"] == pytest.approx(0.5), "minimum je jedan korak"


def test_quantize_prazne_liste():
    assert quantize_notes([], TEMPO) == []


def test_quantize_koristi_stvarnu_mrezu_doba():
    """Kada beat tracker da doba, kvantizacija prati njih, a ne konstantan tempo."""
    # Doba na 0.0, 0.6, 1.2, 1.8 (100 BPM), a nota kasni 40 ms.
    rhythm = RhythmAnalysis(tempo_bpm=100.0, beat_times=[0.0, 0.6, 1.2, 1.8])

    quantized = quantize_notes([make_note(60, 0.64, 1.15)], rhythm, grid=8)

    assert quantized[0]["start"] == pytest.approx(0.6, abs=1e-3)
    assert quantized[0]["start_beat"] == 0.0


# --- tonalitet -----------------------------------------------------------------------


def test_estimate_key_prepoznaje_dur():
    # C-dur lestvica, tonika najduza.
    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 60, 67]
    notes = [make_note(p, i * 0.5, i * 0.5 + 0.45) for i, p in enumerate(pitches)]

    key = estimate_key(notes)

    assert key is not None
    assert key.tonic == "C"
    assert key.mode == "major"
    assert key.name == "C major"


def test_estimate_key_prepoznaje_mol():
    # a-mol: prirodna lestvica sa naglasenom tonikom A.
    pitches = [57, 59, 60, 62, 64, 65, 67, 69, 57, 64, 57]
    notes = [make_note(p, i * 0.5, i * 0.5 + 0.45) for i, p in enumerate(pitches)]

    key = estimate_key(notes)

    assert key is not None and key.mode == "minor"
    assert key.tonic == "A"


def test_estimate_key_bez_nota():
    assert estimate_key([]) is None


def test_snap_to_scale_izbacuje_nesigurne_vanlestvicne_note():
    from notemkr.quantize import KeyEstimate

    key = KeyEstimate("C", "major", 0.9)
    notes = [
        make_note(60, 0.0, 0.5, confidence=0.9),  # C — u lestvici
        make_note(61, 0.5, 1.0, confidence=0.3),  # C# — van lestvice, nesiguran
        make_note(61, 1.0, 1.5, confidence=0.8),  # C# — van lestvice, ali siguran
    ]

    kept = snap_to_scale(notes, key, max_confidence=0.5)

    assert [note["pitch"] for note in kept] == [60, 61]
    assert kept[1]["confidence"] == 0.8


# --- integracija ---------------------------------------------------------------------


@requires_basic_pitch
@requires_sample
def test_analiza_ritma_na_snimku(transcription):
    rhythm = analyze_rhythm(transcription.samples, transcription.sample_rate)

    assert rhythm.tempo_bpm == pytest.approx(120.0, abs=5.0), "test snimak je 120 BPM"
    assert len(rhythm.beat_times) > 10


@requires_basic_pitch
@requires_sample
def test_rezultat_sadrzi_tempo_i_tonalitet(result):
    assert result["tempo_bpm"] == pytest.approx(120.0, abs=5.0)
    assert result["key"] == "G major", "test snimak je u G-duru"
    assert result["time_signature"] == "4/4"


@requires_basic_pitch
@requires_sample
def test_note_su_poravnate_na_mrezu(result):
    notes = result["right_hand"] + result["left_hand"]

    assert notes
    for note in notes:
        assert "start_beat" in note and "duration_beats" in note
        assert note["start_beat"] % 0.5 == 0, "sve pocinje na osmini ili krupnije"
        assert note["duration_beats"] >= 0.5

    assert min(note["start_beat"] for note in notes) == 0.0, "prva nota je pocetak takta"
