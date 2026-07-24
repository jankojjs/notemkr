"""Provera spakovane aplikacije: pokreni je i propusti pravi snimak kroz nju.

    python packaging/smoke_test.py --dist dist --mode onedir

Ovo je test prihvatanja Taska 8 u malom, i to nad *paketom* a ne nad izvornim kodom:

1. pokrene se `notemkr.exe` (bez browsera, sa svojim privremenim jobs folderom);
2. saceka se da server proradi;
3. `/health` mora da javi da je `ffmpeg` nadjen — dokaz da je prilozeni binarni fajl
   u PATH-u (na CI runneru ffmpeg inace nije instaliran);
4. `samples/melodija-test.mp3` se posalje na `/transcribe` i mora da vrati note —
   dokaz da su i ONNX model i ceo pipeline u paketu;
5. proveri se da je frontend (`/`) posluzen iz paketa.

Koristi samo standardnu biblioteku, jer se pusta i tamo gde projekat nije instaliran.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "melodija-test.mp3"

HOST = "127.0.0.1"
STARTUP_TIMEOUT_SEC = 180.0  # prvo pokretanje onefile paketa ume da bude sporo
REQUEST_TIMEOUT_SEC = 600.0  # transkripcija na CI runneru nije brza


def executable_path(dist: Path, mode: str) -> Path:
    """Putanja do izvrsnog fajla u `dist/`, po rezimu gradnje."""
    name = f"notemkr{'.exe' if os.name == 'nt' else ''}"
    candidate = dist / name if mode == "onefile" else dist / "notemkr" / name
    if not candidate.is_file():
        raise SystemExit(
            f"Nema izvrsnog fajla: {candidate}\nSadrzaj {dist}: {list(dist.iterdir())}"
        )
    return candidate


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def wait_for_server(port: int, process: subprocess.Popen, timeout: float) -> None:
    """Cekaj da server pocne da slusa; padni odmah ako proces u medjuvremenu umre."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(
                f"Aplikacija se ugasila pre nego sto je proradila (kod {process.returncode})."
            )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((HOST, port)) == 0:
                return
        time.sleep(0.5)
    raise SystemExit(f"Server se nije javio na portu {port} u {timeout:.0f} s.")


def get_json(url: str) -> dict:
    import json

    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def post_audio(url: str, audio: Path) -> dict:
    """Posalji snimak kao multipart/form-data (bez spoljnih biblioteka)."""
    import json

    boundary = f"----notemkr{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'.encode(),
            b"Content-Type: audio/mpeg\r\n\r\n",
            audio.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"/transcribe je vratio {exc.code}: {detail}") from exc


def check(condition: bool, message: str) -> None:
    print(f"  {'OK  ' if condition else 'PAD '} {message}")
    if not condition:
        raise SystemExit(f"Provera nije prosla: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--mode", choices=("onedir", "onefile"), default="onedir")
    args = parser.parse_args(argv)

    exe = executable_path(args.dist.resolve(), args.mode)
    port = free_port()
    base = f"http://{HOST}:{port}"

    with tempfile.TemporaryDirectory(prefix="notemkr-smoke-") as jobs_dir:
        print(f"Pokrecem: {exe}\n  port {port}, jobs {jobs_dir}")
        process = subprocess.Popen(
            [str(exe), "--host", HOST, "--port", str(port), "--no-browser", "--jobs-dir", jobs_dir],
            cwd=str(exe.parent),
            stdout=None,
            stderr=None,
        )
        try:
            wait_for_server(port, process, STARTUP_TIMEOUT_SEC)
            print("Server radi. Provere:")

            health = get_json(f"{base}/health")
            check(health.get("status") == "ok", f"/health odgovara: {health}")
            check(bool(health.get("ffmpeg")), "prilozeni ffmpeg je nadjen u PATH-u")

            with urllib.request.urlopen(f"{base}/", timeout=30) as page:
                html = page.read().decode("utf-8", "replace")
            check("<html" in html.lower(), "frontend iz web/ se servira")

            check(SAMPLE.is_file(), f"test snimak postoji: {SAMPLE}")
            print(f"  ... saljem {SAMPLE.name} na /transcribe (moze da potraje)")
            result = post_audio(f"{base}/transcribe", SAMPLE)

            status = result.get("status")
            check(status == "done", f"transkripcija gotova (status={status})")
            counts = result.get("note_counts") or {}
            check(
                int(counts.get("right_hand", 0)) + int(counts.get("left_hand", 0)) > 0,
                f"model je vratio note: {counts}",
            )
            check(bool(result.get("musicxml")), "MusicXML je napravljen")
            check(bool((result.get("files") or {}).get("midi")), "MIDI je napravljen")
            print(f"\nTempo {result.get('tempo_bpm')} BPM, tonalitet {result.get('key')}.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:  # pragma: no cover
                process.kill()

    print("\nSve provere su prosle — paket radi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
