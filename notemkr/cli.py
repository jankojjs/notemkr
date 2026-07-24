"""Komandna linija: MP3 -> MIDI + MusicXML (+ PDF).

    notemkr-transcribe pesma.mp3
    python -m notemkr pesma.mp3 -o izlaz/ --grid 16

Izlazni fajlovi se imenuju po ulaznom snimku (`pesma.mid`, `pesma.musicxml`,
`pesma.pdf`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import export_all, find_musescore
from .runtime import prepare_runtime
from .split_hands import DEFAULT_SPLIT_PITCH, HandSplitParams
from .transcribe import TranscriptionParams, transcribe_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notemkr",
        description="Iz MP3 snimka pravi notni zapis za harmoniku (leva + desna ruka).",
    )
    parser.add_argument("audio", type=Path, help="ulazni snimak (MP3, WAV, M4A...)")
    parser.add_argument(
        "-o", "--out-dir", type=Path, default=None,
        help="folder za izlazne fajlove (podrazumevano pored ulaznog snimka)",
    )
    parser.add_argument(
        "--grid", type=int, default=8, choices=(4, 8, 16),
        help="najsitnija podela za kvantizaciju: 4=cetvrtina, 8=osmina, 16=sesnaestina",
    )
    parser.add_argument(
        "--split-pitch", type=int, default=DEFAULT_SPLIT_PITCH,
        help="prag razdvajanja ruku kao MIDI visina (60 = C4)",
    )
    parser.add_argument(
        "--monophonic", action="store_true",
        help="desna ruka kao jedna melodijska linija, bez preklapanja",
    )
    parser.add_argument(
        "--snap-to-scale", action="store_true",
        help="izbaci vanlestvicne note niske pouzdanosti",
    )
    parser.add_argument("--no-quantize", action="store_true", help="preskoci kvantizaciju")
    parser.add_argument("--no-pdf", action="store_true", help="ne pokusavaj PDF izvoz")
    parser.add_argument("--json", action="store_true", help="ispisi rezultat kao JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    prepare_runtime()  # nadji prilozeni ffmpeg ako radimo iz spakovane verzije
    args = build_parser().parse_args(argv)

    params = TranscriptionParams(
        grid=args.grid,
        quantize=not args.no_quantize,
        snap_to_scale=args.snap_to_scale,
        hands=HandSplitParams(
            split_pitch=args.split_pitch,
            monophonic_melody=args.monophonic,
        ),
    )

    result = transcribe_file(args.audio, params)
    if result["status"] != "ok":
        for warning in result["warnings"]:
            print(f"greska: {warning}", file=sys.stderr)
        return 1

    files = export_all(result, out_dir=args.out_dir, with_pdf=not args.no_pdf)

    if args.json:
        print(json.dumps({**result, "files": {k: str(v) for k, v in files.items()}}, indent=2))
        return 0

    print(f"Snimak:    {result['source']}  ({result['duration_sec']:.1f} s)")
    print(f"Tempo:     {result['tempo_bpm']} BPM, taktomer {result['time_signature']}")
    print(f"Tonalitet: {result['key']}")
    print(f"Note:      desna {len(result['right_hand'])}, leva {len(result['left_hand'])}")
    for kind, path in files.items():
        print(f"  {kind:9s} {path if path else '(preskoceno)'}")
    if files["pdf"] is None and not args.no_pdf and find_musescore() is None:
        print("  (PDF preskocen: MuseScore CLI nije nadjen — vidi MUSESCORE_PATH)")
    for warning in result["warnings"]:
        print(f"  upozorenje: {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
