"""Testovi Taska 4: razdvajanje melodije (desna) i basa/akorada (leva ruka).

Acceptance:
- dvostazni MIDI gde je melodija u desnoj, a bas u levoj ruci,
- preklapanja i duplikati ociscen.
"""

from __future__ import annotations

import pytest
from conftest import requires_basic_pitch, requires_sample

from notemkr.notes import make_note
from notemkr.split_hands import (
    HandSplitParams,
    annotate_left_hand,
    identify_chord,
    is_melody_note,
    split_hands,
)

# Melodija test snimka je u opsegu G4-G5, bas i akordi G2-D4.
MELODY_PITCHES = {67, 69, 71, 74, 76, 78, 79}
BASS_PITCHES = {43, 45, 48, 50}


def _bass_and_melody() -> list:
    """Takt pratnje: bas G2, akord G-dur, uz melodiju u desnoj ruci."""
    return [
        make_note(43, 0.0, 0.5),  # G2 — bas
        make_note(67, 0.0, 0.5),  # G4 — melodija
        make_note(55, 0.5, 1.0),  # G3 \
        make_note(59, 0.5, 1.0),  # B3  } akord G-dur u levoj ruci
        make_note(62, 0.5, 1.0),  # D4 /
        make_note(69, 0.5, 1.0),  # A4 — melodija
    ]


# --- skyline -------------------------------------------------------------------------


def test_is_melody_note_bira_gornji_glas():
    notes = _bass_and_melody()

    assert is_melody_note(notes[1], notes), "G4 je najvisa nota u tom trenutku"
    assert not is_melody_note(notes[0], notes), "bas nije gornji glas"


def test_skyline_ne_prekida_izdrzanu_melodiju():
    """Nizi akord ispod izdrzane melodije ne postaje melodija."""
    melody = make_note(72, 0.0, 2.0)  # C5 traje dva takta
    chord = [make_note(48, 1.0, 1.5), make_note(52, 1.0, 1.5), make_note(55, 1.0, 1.5)]
    notes = [melody, *chord]

    right, left = split_hands(notes)

    assert [note["pitch"] for note in right] == [72]
    assert [note["pitch"] for note in left] == [48, 52, 55]


# --- raspodela po rukama -------------------------------------------------------------


def test_split_hands_deli_melodiju_i_pratnju():
    right, left = split_hands(_bass_and_melody())

    assert [note["pitch"] for note in right] == [67, 69]
    assert [note["pitch"] for note in left] == [43, 55, 59, 62]
    assert all(note["hand"] == "right" for note in right)
    assert all(note["hand"] == "left" for note in left)


def test_gornji_ton_akorda_iznad_praga_ostaje_u_levoj():
    """D4 je iznad praga C4, ali pripada akordu ciji je najnizi ton ispod praga."""
    _, left = split_hands(_bass_and_melody())

    assert 62 in [note["pitch"] for note in left]


def test_usamljena_nota_iznad_praga_ide_u_desnu():
    """Ista visina bez akorda ispod nje je pratnja desne ruke, ne bas."""
    notes = [make_note(76, 0.0, 0.5), make_note(62, 0.0, 0.5)]

    right, left = split_hands(notes)

    assert [note["pitch"] for note in right] == [62, 76]
    assert left == []


def test_note_van_opsega_instrumenta_se_odbacuju():
    notes = [
        make_note(30, 0.0, 0.5),  # duboko ispod basa harmonike
        make_note(100, 0.0, 0.5),  # iznad diskanta
        make_note(67, 0.0, 0.5),
    ]

    right, left = split_hands(notes)

    assert [note["pitch"] for note in right] == [67]
    assert left == []


def test_prag_razdvajanja_je_parametrizovan():
    notes = [make_note(64, 0.0, 0.5), make_note(55, 0.0, 0.5)]

    _, left_default = split_hands(notes)
    _, left_visok_prag = split_hands(notes, HandSplitParams(split_pitch=72))

    assert [note["pitch"] for note in left_default] == [55]
    assert [note["pitch"] for note in left_visok_prag] == [55, 64], "vise nota pada levo"


def test_duplikati_se_ciste():
    notes = [
        make_note(67, 0.0, 0.50, confidence=0.5),
        make_note(67, 0.02, 0.90, confidence=0.9),  # isti ton, prakticno isti pocetak
    ]

    right, _ = split_hands(notes)

    assert len(right) == 1
    assert right[0]["end"] == pytest.approx(0.90), "zadrzana je duza/pouzdanija nota"


def test_monofona_melodija_uklanja_preklapanja():
    notes = [make_note(67, 0.0, 2.0), make_note(71, 1.0, 2.0)]

    right, _ = split_hands(notes, HandSplitParams(monophonic_melody=True))

    assert len(right) == 2
    assert right[0]["end"] == pytest.approx(1.0), "prva nota je skracena do sledece"
    assert right[1]["start"] == pytest.approx(1.0)


def test_prazan_ulaz():
    assert split_hands([]) == ([], [])


# --- Stradella akordi ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("pitches", "label", "quality"),
    [
        ([55, 59, 62], "G", "dur"),  # G-dur
        ([57, 60, 64], "Am", "mol"),  # a-mol
        ([50, 54, 57, 60], "D7", "sept"),  # D7
        ([50, 54, 60], "D7", "sept"),  # D7 bez kvinte (tipicno za Stradella)
        ([59, 62, 65], "Bdim", "umanjen"),  # umanjen
    ],
)
def test_identify_chord(pitches, label, quality):
    chord = identify_chord(pitches)

    assert chord is not None
    assert chord["label"] == label
    assert chord["quality"] == quality


def test_identify_chord_odbija_nepoznat_sklop():
    assert identify_chord([60, 61, 62]) is None
    assert identify_chord([60, 67]) is None, "dva tona nisu akord"


def test_annotate_left_hand_oznacava_bas_i_akord():
    notes = [
        make_note(43, 0.0, 0.5),  # G2 bas
        make_note(55, 0.5, 1.0),
        make_note(59, 0.5, 1.0),
        make_note(62, 0.5, 1.0),
    ]

    annotated = annotate_left_hand(notes)

    assert annotated[0]["role"] == "bass"
    assert all(note["role"] == "chord" for note in annotated[1:])
    assert all(note["chord"]["label"] == "G" for note in annotated[1:])


def test_annotate_left_hand_koristi_izdrzane_tonove():
    """Akord se prepoznaje i kad osnovni ton traje jos od prethodne dobe."""
    notes = [
        make_note(48, 0.0, 2.0),  # C3 traje ispod
        make_note(52, 1.0, 1.5),  # E3
        make_note(55, 1.0, 1.5),  # G3
    ]

    annotated = annotate_left_hand(notes)
    later = [note for note in annotated if note["start"] == 1.0]

    assert [note["chord"]["label"] for note in later] == ["C", "C"]


# --- integracija ---------------------------------------------------------------------


@requires_basic_pitch
@requires_sample
def test_melodija_je_u_desnoj_a_bas_u_levoj(result):
    right = {note["pitch"] for note in result["right_hand"]}
    left = {note["pitch"] for note in result["left_hand"]}

    assert len(right & MELODY_PITCHES) >= 5, "melodija je prepoznata u desnoj ruci"
    assert len(left & BASS_PITCHES) >= 3, "bas je u levoj ruci"
    assert not (right & BASS_PITCHES), "bas tonovi ne cure u desnu ruku"


@requires_basic_pitch
@requires_sample
def test_leva_ruka_ima_prepoznate_akorde(result):
    labels = {note["chord"]["label"] for note in result["left_hand"] if "chord" in note}

    assert {"G", "C", "D"} <= labels, "harmonija test snimka je G-C-D"


@requires_basic_pitch
@requires_sample
def test_izvoz_dvostaznog_midija(result, tmp_path):
    """Acceptance: `.mid` sa dve staze — Track 1 desna, Track 2 leva ruka."""
    import pretty_midi

    from notemkr.export import export_midi

    out = export_midi(result, tmp_path / "razdvojeno.mid")
    midi = pretty_midi.PrettyMIDI(str(out))

    assert len(midi.instruments) == 2
    right_track, left_track = midi.instruments
    assert len(right_track.notes) == len(result["right_hand"])
    assert len(left_track.notes) == len(result["left_hand"])

    # Desna ruka svira u proseku znatno vise od leve.
    right_mean = sum(n.pitch for n in right_track.notes) / len(right_track.notes)
    left_mean = sum(n.pitch for n in left_track.notes) / len(left_track.notes)
    assert right_mean > left_mean + 10
