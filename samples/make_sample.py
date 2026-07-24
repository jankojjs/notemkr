"""Generise kratak test MP3 (harmonika-nalik) za testove pipeline-a.

Snimak je namerno jednostavan i deterministican: melodija u desnom registru +
bas/akordi u levom, 4/4, 120 BPM, G-dur. Sluzi kao ulaz za acceptance testove
(MP3 -> note -> MIDI/MusicXML) bez potrebe za pravim snimkom pod autorskim pravima.

Pokretanje (iz korena repozitorijuma, sa aktiviranim venv-om):

    python samples/make_sample.py

Zahteva `ffmpeg` u PATH-u (za MP3 enkodiranje).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 44100
BPM = 120.0
BEAT = 60.0 / BPM  # 0.5 s

OUT_PATH = Path(__file__).resolve().parent / "melodija-test.mp3"

# Melodija (desna ruka), G-dur: (MIDI pitch, trajanje u dobama).
# G4=67, A4=69, H4=71, C5=72, D5=74, E5=76, Fis5=78, G5=79
MELODY: list[tuple[int, float]] = [
    (67, 1.0), (69, 1.0), (71, 1.0), (74, 1.0),
    (76, 1.0), (74, 1.0), (71, 1.0), (69, 1.0),
    (67, 1.0), (71, 1.0), (74, 1.0), (79, 1.0),
    (78, 1.0), (74, 1.0), (71, 2.0),
]

# Bas / leva ruka: naizmenicno osnovni ton (doba 1 i 3) i akord (doba 2 i 4),
# kao klasicna "bas-akord" pratnja na harmonici. G2=43, D3=50, C3=48, A2=45.
BASS_PATTERN: list[tuple[tuple[int, ...], float]] = [
    ((43,), 1.0), ((55, 59, 62), 1.0), ((50,), 1.0), ((55, 59, 62), 1.0),  # G   akord G-dur
    ((48,), 1.0), ((52, 55, 60), 1.0), ((43,), 1.0), ((52, 55, 60), 1.0),  # C   akord C-dur
    ((45,), 1.0), ((52, 57, 61), 1.0), ((50,), 1.0), ((54, 57, 62), 1.0),  # a-mol, D-dur
    ((43,), 1.0), ((55, 59, 62), 1.0), ((43,), 2.0),                       # G
]

# Relativne amplitude harmonika — daju "trskasti" (reed) ton nalik harmonici;
# cist sinus je losiji ulaz za basic-pitch od tona bogatog harmonicima.
HARMONICS = (1.0, 0.6, 0.35, 0.22, 0.14, 0.08)


def midi_to_hz(pitch: int) -> float:
    return 440.0 * 2.0 ** ((pitch - 69) / 12.0)


def render_note(pitch: int, duration_sec: float, amplitude: float) -> np.ndarray:
    """Jedan ton sa harmonicima i blagom ADSR anvelopom."""
    n = int(duration_sec * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    freq = midi_to_hz(pitch)

    wave = np.zeros(n, dtype=np.float64)
    for k, level in enumerate(HARMONICS, start=1):
        if freq * k > SAMPLE_RATE / 2:  # ne prelazi Nyquist
            break
        wave += level * np.sin(2 * np.pi * freq * k * t)
    wave /= sum(HARMONICS)

    # ADSR: brz napad, kratak pad, sustain, pa release do kraja tona.
    env = np.ones(n)
    attack = max(1, int(0.02 * SAMPLE_RATE))
    release = max(1, int(0.06 * SAMPLE_RATE))
    env[:attack] = np.linspace(0.0, 1.0, attack)
    env[n - release:] = np.linspace(1.0, 0.0, release)

    return wave * env * amplitude


def render_track(events: list[tuple[tuple[int, ...], float]], amplitude: float) -> np.ndarray:
    """Sekvencijalno nizanje (moguce viseglasnih) dogadjaja u jedan signal."""
    total = sum(dur for _, dur in events) * BEAT
    buf = np.zeros(int(total * SAMPLE_RATE) + SAMPLE_RATE, dtype=np.float64)

    cursor = 0.0
    for pitches, beats in events:
        dur = beats * BEAT * 0.92  # mali razmak izmedju tonova (detache)
        start = int(cursor * SAMPLE_RATE)
        for pitch in pitches:
            note = render_note(pitch, dur, amplitude / max(1, len(pitches)) ** 0.5)
            buf[start:start + len(note)] += note
        cursor += beats * BEAT

    return buf


def main() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg nije u PATH-u — potreban je za MP3 enkodiranje.")

    melody = render_track([((p,), d) for p, d in MELODY], amplitude=0.55)
    bass = render_track(BASS_PATTERN, amplitude=0.40)

    length = max(len(melody), len(bass))
    mix = np.zeros(length)
    mix[:len(melody)] += melody
    mix[:len(bass)] += bass
    mix /= max(1e-9, np.max(np.abs(mix))) / 0.89  # normalizacija bez klipovanja

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        sf.write(str(wav_path), mix.astype(np.float32), SAMPLE_RATE)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-b:a", "128k", str(OUT_PATH)],
            check=True,
        )

    print(f"Napisano: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB, "
          f"{length / SAMPLE_RATE:.1f} s)")


if __name__ == "__main__":
    main()
