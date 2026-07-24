"""Testovi Taska 2: MP3 -> note (basic-pitch, ONNX).

Acceptance:
- za kratak melodijski MP3 se generise `.mid` sa prepoznatim notama,
- radi bez TensorFlow-a (samo onnxruntime).
"""

from __future__ import annotations

import sys

import pytest
from conftest import requires_basic_pitch, requires_sample

from notemkr.audio import AudioLoadError, audio_duration, load_audio
from notemkr.notes import BASE_KEYS
from notemkr.transcribe import (
    ACCORDION_MAX_PITCH,
    ACCORDION_MIN_PITCH,
    TranscriptionParams,
    _drop_ghosts,
    _merge_repeated,
    extract_notes,
)

# Melodija iz test snimka (samples/make_sample.py), G-dur.
EXPECTED_MELODY_PITCHES = {67, 69, 71, 74, 76, 78, 79}
EXPECTED_BASS_PITCHES = {43, 45, 48, 50}


# --- audio dekodiranje ---------------------------------------------------------------


@requires_sample
def test_load_audio_daje_mono_22050(sample_mp3):
    samples, sample_rate = load_audio(sample_mp3)

    assert sample_rate == 22050
    assert samples.ndim == 1
    assert samples.size > 0
    assert float(abs(samples).max()) <= 1.0


@requires_sample
def test_audio_duration_odgovara_snimku(sample_mp3):
    assert audio_duration(sample_mp3) == pytest.approx(9.0, abs=0.3)


def test_load_audio_prijavljuje_nepostojeci_fajl(tmp_path):
    with pytest.raises(AudioLoadError):
        load_audio(tmp_path / "nema-me.mp3")


# --- ciscenje nota (bez modela) ------------------------------------------------------


def test_merge_repeated_spaja_izdeljen_ton():
    notes = [
        {"pitch": 67, "start": 0.0, "end": 0.40, "velocity": 80, "confidence": 0.7},
        {"pitch": 67, "start": 0.43, "end": 0.90, "velocity": 90, "confidence": 0.6},
        {"pitch": 67, "start": 2.00, "end": 2.40, "velocity": 70, "confidence": 0.6},
    ]

    merged = _merge_repeated(notes)

    assert len(merged) == 2, "dva bliska fragmenta su ista nota, treci je nova nota"
    assert merged[0]["end"] == pytest.approx(0.90)
    assert merged[0]["velocity"] == 90


def test_drop_ghosts_izbacuje_tisi_harmonik():
    prava = {"pitch": 62, "start": 1.0, "end": 1.5, "velocity": 90, "confidence": 0.80}
    duh = {"pitch": 74, "start": 1.01, "end": 1.4, "velocity": 50, "confidence": 0.40}
    glasna_oktava = {"pitch": 86, "start": 1.0, "end": 1.5, "velocity": 95, "confidence": 0.85}

    keep = _drop_ghosts([prava, duh, glasna_oktava])

    assert prava in keep
    assert duh not in keep, "oktava iznad, isti pocetak, bitno manja pouzdanost = harmonik"
    assert glasna_oktava in keep, "glasnija nota se ne odbacuje kao duh"


# --- integracija sa basic-pitch ------------------------------------------------------


@requires_basic_pitch
@requires_sample
def test_bez_tensorflow_a(transcription):
    """Acceptance: pipeline radi samo sa onnxruntime, bez TensorFlow-a."""
    assert "onnxruntime" in sys.modules
    assert "tensorflow" not in sys.modules


@requires_basic_pitch
@requires_sample
def test_prepoznaje_note_iz_mp3(transcription):
    assert transcription.duration_sec == pytest.approx(9.0, abs=0.3)
    assert len(transcription.notes) > 20, "test snimak ima ~30 tonova"

    for note in transcription.notes:
        assert set(BASE_KEYS) <= set(note)
        assert ACCORDION_MIN_PITCH <= note["pitch"] <= ACCORDION_MAX_PITCH
        assert note["end"] > note["start"]
        assert 1 <= note["velocity"] <= 127


@requires_basic_pitch
@requires_sample
def test_pogadja_melodiju_i_bas(transcription):
    detected = {note["pitch"] for note in transcription.notes}

    assert len(detected & EXPECTED_MELODY_PITCHES) >= 5, "vecina melodije je prepoznata"
    assert len(detected & EXPECTED_BASS_PITCHES) >= 3, "bas tonovi su prepoznati"


@requires_basic_pitch
@requires_sample
def test_pise_midi_fajl(transcription, tmp_path):
    """Acceptance: iz MP3-a nastaje `.mid` sa prepoznatim notama."""
    import pretty_midi

    out = tmp_path / "melodija-test.mid"
    transcription.to_pretty_midi().write(str(out))

    assert out.is_file() and out.stat().st_size > 0

    reloaded = pretty_midi.PrettyMIDI(str(out))
    assert len(reloaded.instruments) == 1
    assert len(reloaded.instruments[0].notes) == len(transcription.notes)


@requires_basic_pitch
@requires_sample
def test_parametri_suzavaju_opseg(sample_mp3):
    """Min/max visina se prosledjuje modelu i filtrira note van opsega."""
    uzak = extract_notes(sample_mp3, TranscriptionParams(min_pitch=60, max_pitch=72))

    assert uzak.notes, "u opsegu C4-C5 ima nota"
    assert all(60 <= note["pitch"] <= 72 for note in uzak.notes)


def test_transcribe_file_vraca_gresku_umesto_izuzetka(tmp_path):
    from notemkr import transcribe_file

    result = transcribe_file(tmp_path / "nema-me.mp3")

    assert result["status"] == "error"
    assert result["right_hand"] == [] and result["left_hand"] == []
    assert result["warnings"], "greska se vraca korisniku kao upozorenje"
