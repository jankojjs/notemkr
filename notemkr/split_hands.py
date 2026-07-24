"""Razdvajanje toka nota na desnu (melodija) i levu ruku (bas/akordi).

Za harmoniku je ovo kljucni korak: desna ruka svira melodiju u diskantu, a leva
bas i akorde na Stradella basu. Postupak:

1. **Skyline** — nota je melodija ako u trenutku svog pocetka nijedna visa nota
   ne zvuci. Time sustinski dobijamo gornji glas, i kada se ispod njega menjaju
   akordi (jer sustinski nizi tonovi ne prekidaju vec zapocetu melodiju).
2. **Opsezi** — sve van opsega instrumenta se odbacuje, sto je ispod desne ruke
   ide levo, a pratnja iznad opsega leve ruke ostaje u desnoj.
3. **Akordi** — istovremene note u levoj ruci se grupisu i prepoznaju kao
   Stradella akord (osnovni ton + dur/mol/sept/umanjen).

Sve granice su parametrizovane (`HandSplitParams`) — podrazumevane vrednosti su
za klavirsku harmoniku.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .notes import PITCH_CLASS_NAMES, Note, sort_notes

# Opsezi (MIDI visine). Desna ruka (diskant) F3-A6; leva ruka: basovi F2-C4, dok
# Stradella akordi zvuce nesto vise, do oko E4 — otuda `left_max` iznad C4.
DEFAULT_RIGHT_MIN = 53  # F3
DEFAULT_RIGHT_MAX = 93  # A6
DEFAULT_LEFT_MIN = 41  # F2
DEFAULT_LEFT_MAX = 64  # E4
DEFAULT_SPLIT_PITCH = 60  # C4 — orijentaciona granica izmedju ruku

# Note koje pocinju blize od ovoga smatramo istovremenim (akord / isti udar).
SIMULTANEITY_SEC = 0.08

# Oblici akorda koje Stradella bas moze da odsvira: interval-obrasci od osnovnog
# tona -> (tip, oznaka u nazivu akorda).
CHORD_SHAPES: dict[tuple[int, ...], tuple[str, str]] = {
    (0, 4, 7): ("dur", ""),
    (0, 3, 7): ("mol", "m"),
    (0, 4, 7, 10): ("sept", "7"),
    (0, 4, 10): ("sept", "7"),  # sept bez kvinte — tipicno za Stradella bas
    (0, 3, 7, 10): ("mol-sept", "m7"),
    (0, 3, 6): ("umanjen", "dim"),
    (0, 3, 6, 9): ("umanjen", "dim7"),
}


@dataclass(slots=True)
class HandSplitParams:
    """Granice i pravila razdvajanja ruku."""

    split_pitch: int = DEFAULT_SPLIT_PITCH
    right_min: int = DEFAULT_RIGHT_MIN
    right_max: int = DEFAULT_RIGHT_MAX
    left_min: int = DEFAULT_LEFT_MIN
    left_max: int = DEFAULT_LEFT_MAX
    monophonic_melody: bool = False  # desna ruka kao jedna linija, bez preklapanja
    detect_chords: bool = True


def is_melody_note(note: Note, notes: list[Note], tolerance: float = SIMULTANEITY_SEC) -> bool:
    """Da li je nota gornji glas ("skyline") u trenutku svog pocetka."""
    start = float(note["start"])
    return not any(
        other is not note
        and int(other["pitch"]) > int(note["pitch"])
        and float(other["start"]) <= start + tolerance
        and float(other["end"]) > start + tolerance
        for other in notes
    )


def _assign_hand(
    note: Note,
    melody: bool,
    lowest_together: int,
    params: HandSplitParams,
) -> str | None:
    """Odredi ruku za jednu notu: `"right"`, `"left"` ili `None` (van opsega).

    Args:
        note: Nota koja se rasporedjuje.
        melody: Da li je nota gornji glas u trenutku pocetka (skyline).
        lowest_together: Najniza visina medju notama koje pocinju istovremeno —
            po njoj se prepoznaje da nota pripada akordu leve ruke.
        params: Granice opsega i prag razdvajanja.
    """
    pitch = int(note["pitch"])

    if not params.left_min <= pitch <= params.right_max:
        return None  # van opsega instrumenta — skoro sigurno artefakt
    if pitch < params.split_pitch:
        return "left"
    # Iznad praga: jos uvek leva ruka ako nota nije melodija, a jeste gornji ton
    # akorda ciji najnizi ton lezi ispod praga (Stradella akordi zvuce iznad basa,
    # do oko E4).
    if not melody and pitch <= params.left_max and lowest_together < params.split_pitch:
        return "left"
    if pitch < params.right_min:
        return "left"  # desna ruka ne dopire tako nisko
    return "right"


def _dedupe(notes: list[Note], tolerance: float = SIMULTANEITY_SEC) -> list[Note]:
    """Izbaci duplikate — istu visinu koja pocinje prakticno u istom trenutku."""
    kept: list[Note] = []
    for note in sort_notes(notes):
        twin = next(
            (
                other
                for other in kept
                if other["pitch"] == note["pitch"]
                and abs(float(other["start"]) - float(note["start"])) <= tolerance
            ),
            None,
        )
        if twin is None:
            kept.append(note)
            continue
        # Zadrzi duzu, odnosno pouzdaniju od dve.
        if _score(note) > _score(twin):
            kept[kept.index(twin)] = note
    return kept


def _score(note: Note) -> tuple[float, float]:
    return (float(note["end"]) - float(note["start"]), float(note.get("confidence", 0.0)))


def _trim_overlaps(notes: list[Note]) -> list[Note]:
    """Skrati note tako da se linija ne preklapa sama sa sobom (monofona melodija)."""
    ordered = sort_notes(notes)
    trimmed: list[Note] = []

    for index, note in enumerate(ordered):
        current = dict(note)
        following = next(
            (o for o in ordered[index + 1 :] if float(o["start"]) > float(current["start"])),
            None,
        )
        if following is not None and float(current["end"]) > float(following["start"]):
            current["end"] = float(following["start"])
            if "duration_beats" in current and "start_beat" in following:
                current["duration_beats"] = round(
                    float(following["start_beat"]) - float(current["start_beat"]), 4
                )
        if current["end"] > current["start"]:
            trimmed.append(current)

    return trimmed


def _keep_highest_per_onset(notes: list[Note]) -> list[Note]:
    """Od istovremenih nota zadrzi samo najvisu (jedna linija u desnoj ruci)."""
    kept: list[Note] = []
    for group in group_simultaneous(notes):
        kept.append(max(group, key=lambda n: int(n["pitch"])))
    return kept


def group_simultaneous(
    notes: list[Note], tolerance: float = SIMULTANEITY_SEC
) -> list[list[Note]]:
    """Grupisi note koje pocinju u istom trenutku (akord ili isti udar)."""
    groups: list[list[Note]] = []
    for note in sort_notes(notes):
        if groups and abs(float(note["start"]) - float(groups[-1][0]["start"])) <= tolerance:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def identify_chord(pitches: list[int]) -> dict[str, str] | None:
    """Prepoznaj Stradella akord iz istovremenih visina.

    Returns:
        `{"root": "G", "quality": "dur", "label": "G"}` ili `None` ako skup tonova
        ne odgovara nijednom obliku koji leva ruka moze da odsvira.
    """
    pitch_classes = sorted({int(pitch) % 12 for pitch in pitches})
    if len(pitch_classes) < 3:
        return None

    for root in pitch_classes:
        shape = tuple(sorted((pc - root) % 12 for pc in pitch_classes))
        match = CHORD_SHAPES.get(shape)
        if match is not None:
            quality, suffix = match
            root_name = PITCH_CLASS_NAMES[root]
            return {"root": root_name, "quality": quality, "label": f"{root_name}{suffix}"}

    return None


def annotate_left_hand(notes: list[Note]) -> list[Note]:
    """Oznaci note leve ruke kao bas ili akord i dodaj naziv akorda.

    Svaka nota dobija `role` ("bass" ili "chord"), a clanovi prepoznatog akorda i
    `chord` sa osnovnim tonom i tipom (dur/mol/sept/umanjen).
    """
    annotated: list[Note] = []

    for group in group_simultaneous(notes):
        # Akord se prepoznaje po svemu sto tada zvuci, ne samo po notama koje bas
        # tada pocinju — bas na prvoj dobi cesto traje ispod akorda na drugoj.
        moment = float(group[0]["start"]) + SIMULTANEITY_SEC
        sounding = [
            note["pitch"]
            for note in notes
            if float(note["start"]) <= moment < float(note["end"])
        ]
        chord = identify_chord(sounding)
        # Oktava ili udvojen isti ton je i dalje bas, a ne akord.
        is_chord = len({int(note["pitch"]) % 12 for note in group}) > 1

        for note in group:
            marked = dict(note)
            marked["role"] = "chord" if is_chord else "bass"
            if chord is not None:
                marked["chord"] = chord
            annotated.append(marked)

    return sort_notes(annotated)


def split_hands(
    notes: list[Note],
    params: HandSplitParams | None = None,
) -> tuple[list[Note], list[Note]]:
    """Razdvoji note na `(desna_ruka, leva_ruka)`.

    Args:
        notes: Note celog snimka (idealno vec kvantizovane).
        params: Granice opsega i pravila; podrazumevano `HandSplitParams()`.

    Returns:
        Dve liste nota. Svaka nota nosi i `hand` ("right"/"left"); note leve ruke
        dodatno `role` i, kad je prepoznat, `chord`. Note van opsega instrumenta
        se odbacuju, a duplikati ciste.
    """
    params = params or HandSplitParams()
    if not notes:
        return [], []

    cleaned = _dedupe(notes)
    right: list[Note] = []
    left: list[Note] = []

    for group in group_simultaneous(cleaned):
        lowest_together = min(int(note["pitch"]) for note in group)
        for note in group:
            hand = _assign_hand(
                note, is_melody_note(note, cleaned), lowest_together, params
            )
            if hand is None:
                continue
            assigned = dict(note)
            assigned["hand"] = hand
            (right if hand == "right" else left).append(assigned)

    if params.monophonic_melody:
        right = _trim_overlaps(_keep_highest_per_onset(right))

    if params.detect_chords:
        left = annotate_left_hand(left)

    return sort_notes(right), sort_notes(left)


def hand_summary(right: list[Note], left: list[Note]) -> dict[str, Any]:
    """Kratak pregled razdvajanja (za upozorenja i web prikaz)."""
    chords = [note["chord"]["label"] for note in left if "chord" in note]
    return {
        "right_count": len(right),
        "left_count": len(left),
        "chords": sorted(set(chords)),
    }
