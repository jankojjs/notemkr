"""Ulazna tacka spakovane aplikacije: dupli klik -> server + otvoren browser.

Razlika u odnosu na `notemkr.server:main` (konzolna komanda za razvoj) je u tome sto
ovde nema nikoga da procita gresku iz terminala niti da izabere drugi port. Zato ovaj
modul:

* pripremi okruzenje (prilozeni `ffmpeg` u PATH) pre nego sto pipeline krene;
* sam nadje slobodan port ako je podrazumevani zauzet (npr. app je vec pokrenuta);
* saceka da server *stvarno* pocne da slusa pa tek onda otvori browser;
* ispise kratko uputstvo na srpskom i, ako pukne, zadrzi prozor otvoren da se
  poruka o gresci vidi (inace se crni prozor na Windows-u zatvori u istom trenu).

Isti modul radi i iz izvornog koda (`python -m notemkr.launcher`), sto ga cini
proverljivim bez pravljenja .exe-a.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

from .runtime import app_dir, bundled_ffmpeg, default_jobs_dir, is_frozen, prepare_runtime
from .server import DEFAULT_HOST, DEFAULT_PORT, create_app

# Ako je podrazumevani port zauzet, probamo redom sledecih nekoliko.
PORT_SCAN_ATTEMPTS = 20

# Koliko cekamo da server pocne da slusa pre nego sto ipak otvorimo browser.
STARTUP_TIMEOUT_SEC = 90.0
STARTUP_POLL_SEC = 0.25

BANNER_WIDTH = 64


def find_free_port(host: str, preferred: int, attempts: int = PORT_SCAN_ATTEMPTS) -> int:
    """Vrati prvi slobodan port pocev od `preferred`.

    Ako je i posle `attempts` pokusaja sve zauzeto, vraca `preferred` — neka onda
    server pukne sa svojom (jasnijom) porukom, umesto da mi ovde nagadjamo.
    """
    for offset in range(max(1, attempts)):
        port = preferred + offset
        if port > 65535:
            break
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    return preferred


def wait_until_serving(
    host: str,
    port: int,
    timeout: float = STARTUP_TIMEOUT_SEC,
    poll: float = STARTUP_POLL_SEC,
) -> bool:
    """Cekaj dok se server ne javi na `host:port`; `False` ako istekne vreme."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(poll)
    return False


def open_browser_when_ready(host: str, port: int, url: str) -> threading.Thread:
    """U pozadini sacekaj da server proradi, pa otvori podrazumevani browser."""

    def worker() -> None:
        if wait_until_serving(host, port):
            try:
                webbrowser.open(url)
            except Exception:  # pragma: no cover - browser je "lepo imati", ne uslov
                print(f"Ne mogu sam da otvorim browser. Otvori rucno: {url}")
        else:  # pragma: no cover - server se nije podigao na vreme
            print(f"Server se sporo podize. Ako se stranica ne otvori, probaj: {url}")

    thread = threading.Thread(target=worker, name="notemkr-browser", daemon=True)
    thread.start()
    return thread


def print_banner(url: str) -> None:
    """Kratko uputstvo za nekoga ko nikada nije video terminal."""
    line = "=" * BANNER_WIDTH
    print(line)
    print("  notemkr — iz snimka pravi note".center(BANNER_WIDTH))
    print(line)
    print(f"  Stranica:  {url}")
    print("  Otvara se sama u browseru (moze da potraje koji sekund).")
    print()
    print("  OVAJ PROZOR MORA DA OSTANE OTVOREN dok radis sa aplikacijom.")
    print("  Kada zavrsis, samo ga zatvori (ili pritisni Ctrl+C).")
    print(line)

    if bundled_ffmpeg() is None:
        from .audio import ffmpeg_available

        if not ffmpeg_available():
            print("  UPOZORENJE: 'ffmpeg' nije nadjen — MP3 snimci se mozda nece ucitati.")
            print(line)
    print(f"  Radni folder: {default_jobs_dir()}")
    print(line, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notemkr",
        description="Pokreni notemkr (lokalni server + browser).",
    )
    parser.add_argument("--host", default=os.environ.get("NOTEMKR_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("NOTEMKR_PORT", DEFAULT_PORT)),
        help="pocetni port; ako je zauzet, uzima se prvi sledeci slobodan",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="ne otvaraj browser pri pokretanju"
    )
    parser.add_argument(
        "--jobs-dir", default=None, help="folder za rezultate (podrazumevano korisnicki folder)"
    )
    return parser


def _hold_window(message: str) -> None:
    """Zadrzi konzolu otvorenu da korisnik stigne da procita poruku o gresci.

    Ima smisla samo u spakovanoj aplikaciji koju je neko pokrenuo duplim klikom;
    u terminalu (ili bez stdin-a, npr. pod CI-jem) samo bi blokiralo.
    """
    if not is_frozen() or not sys.stdin or not sys.stdin.isatty():
        return
    try:
        input(message)
    except (EOFError, KeyboardInterrupt):  # pragma: no cover
        pass


def main(argv: list[str] | None = None) -> int:
    """Pokreni aplikaciju; vraca izlazni kod procesa."""
    prepare_runtime()  # prilozeni ffmpeg u PATH — pre nego sto pipeline zatreba dekoder

    args = build_parser().parse_args(argv)

    try:
        import uvicorn

        port = find_free_port(args.host, args.port)
        if port != args.port:
            print(f"Port {args.port} je zauzet — koristim {port}.")

        url = f"http://{args.host}:{port}/"
        app = create_app(jobs_dir=args.jobs_dir)

        print_banner(url)
        if not args.no_browser:
            open_browser_when_ready(args.host, port, url)

        uvicorn.run(app, host=args.host, port=port, log_level="warning")
    except KeyboardInterrupt:  # pragma: no cover - normalan izlaz na Ctrl+C
        print("\nnotemkr je zaustavljen. Prijatno!")
        return 0
    except Exception as exc:
        print()
        print("notemkr nije mogao da se pokrene.")
        print(f"Razlog: {type(exc).__name__}: {exc}")
        print(f"Aplikacija je u folderu: {app_dir()}")
        _hold_window("\nPritisni Enter da zatvoris ovaj prozor... ")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
