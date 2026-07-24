"""Preuzmi staticki `ffmpeg` u `packaging/vendor/<os>/`, da udje u PyInstaller paket.

    python packaging/fetch_ffmpeg.py            # za tekucu platformu
    python packaging/fetch_ffmpeg.py --os windows

Zasto uopste: `librosa` dekodira MP3/M4A preko `ffmpeg`-a. Na masini bez Python-a
nema ni ffmpeg-a, a od oca se ne moze traziti da ga instalira — pa ga prilazemo.
Mora da bude **staticki** build (bez spoljnih .dll/.dylib fajlova), inace se na
tudjoj masini nece pokrenuti.

Windows: staticki LGPL build (BtbN/FFmpeg-Builds, tag `latest` — uvek postoji), uz
         gyan.dev kao rezervu. LGPL varijanta je namerno izabrana: nema GPL-only
         delova (x264 i slicno), koji nam za dekodiranje MP3/AAC ionako ne trebaju,
         pa je i deljenje gotovog paketa jednostavnije.
macOS:   staticki build sa evermeet.cx (postoji samo za Intel; na Apple Silicon-u
         radi kroz Rosettu, ali je pouzdanije koristiti `brew install ffmpeg` —
         zato Mac verzija i nije glavni deliverable ovog taska).

Ogledala se probaju redom: gradnja .exe-a ne sme da padne zato sto je jedan sajt
trenutno nedostupan (gyan.dev ume da vrati 503).

Skripta je jedina stvar u projektu kojoj treba internet, i to samo pri gradnji
paketa — sama aplikacija radi potpuno offline.
"""

from __future__ import annotations

import argparse
import io
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
VENDOR_DIR = PACKAGING_DIR / "vendor"

# os -> (naziv fajla u arhivi i na disku, ogledala redom kojim se probaju)
SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "windows": (
        "ffmpeg.exe",
        (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-lgpl.zip",
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        ),
    ),
    "macos": (
        "ffmpeg",
        ("https://evermeet.cx/ffmpeg/getrelease/zip",),
    ),
}

PLATFORM_ALIASES = {"win32": "windows", "cygwin": "windows", "darwin": "macos"}

DOWNLOAD_TIMEOUT_SEC = 300


def current_os() -> str:
    """Naziv platforme onako kako ga koriste `SOURCES` i `notemkr.spec`."""
    return PLATFORM_ALIASES.get(sys.platform, "linux")


def _extract_member(payload: bytes, wanted_name: str) -> bytes:
    """Nadji `wanted_name` u ZIP/TAR arhivi i vrati njegov sadrzaj.

    Trazi se po *nazivu fajla* (bez foldera), jer svaki build pakuje ffmpeg u
    drugacije imenovan koren (`ffmpeg-7.1-essentials_build/bin/ffmpeg.exe`...).
    """
    buffer = io.BytesIO(payload)

    if zipfile.is_zipfile(buffer):
        with zipfile.ZipFile(buffer) as archive:
            for name in archive.namelist():
                if name.rsplit("/", 1)[-1] == wanted_name:
                    return archive.read(name)
        raise LookupError(f"U ZIP arhivi nema '{wanted_name}'.")

    buffer.seek(0)
    try:
        with tarfile.open(fileobj=buffer, mode="r:*") as archive:
            for member in archive.getmembers():
                if member.isfile() and Path(member.name).name == wanted_name:
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
    except tarfile.TarError as exc:
        raise LookupError(f"Arhiva nije ni ZIP ni TAR: {exc}") from exc

    raise LookupError(f"U TAR arhivi nema '{wanted_name}'.")


def fetch(target_os: str, force: bool = False) -> Path:
    """Preuzmi i raspakuj ffmpeg za `target_os`; vrati putanju do binarnog fajla."""
    if target_os not in SOURCES:
        raise SystemExit(
            f"Nepoznata platforma '{target_os}'. Podrzano: {', '.join(SOURCES)}.\n"
            "Na Linux-u koristi sistemski ffmpeg (`apt install ffmpeg`)."
        )

    member, mirrors = SOURCES[target_os]
    destination = VENDOR_DIR / target_os / member

    if destination.is_file() and not force:
        print(f"Vec postoji: {destination}  (--force da preuzmes ponovo)")
        return destination

    content: bytes | None = None
    failures: list[str] = []
    for url in mirrors:
        print(f"Preuzimam ffmpeg za {target_os}:\n  {url}")
        try:
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SEC) as response:
                payload = response.read()
            print(f"  preuzeto {len(payload) / 1024 / 1024:.1f} MB, trazim '{member}'...")
            content = _extract_member(payload, member)
            break
        except Exception as exc:
            print(f"  ne valja ovo ogledalo: {exc}")
            failures.append(f"{url}: {exc}")

    if content is None:
        raise RuntimeError("nijedno ogledalo nije uspelo:\n  " + "\n  ".join(failures))

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"  -> {destination}  ({len(content) / 1024 / 1024:.1f} MB)")
    return destination


def copy_system_ffmpeg(target_os: str) -> Path | None:
    """Rezerva: kopiraj `ffmpeg` iz PATH-a (koristi se kad preuzimanje ne uspe).

    Sistemski ffmpeg cesto zavisi od biblioteka koje na tudjoj masini ne postoje
    (npr. Homebrew dylib-ovi), pa je ovo dobro samo za lokalnu probu builda.
    """
    system = shutil.which("ffmpeg")
    if not system:
        return None
    destination = VENDOR_DIR / target_os / Path(system).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(system, destination)
    print(f"Kopiran sistemski ffmpeg: {system} -> {destination}")
    print("UPOZORENJE: sistemski build mozda nije samostalan — dobar samo za lokalni test.")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--os", dest="target_os", default=current_os(), choices=sorted(SOURCES))
    parser.add_argument("--force", action="store_true", help="preuzmi i ako vec postoji")
    parser.add_argument(
        "--allow-system-fallback",
        action="store_true",
        help="ako preuzimanje ne uspe, kopiraj ffmpeg iz PATH-a (samo za lokalni test)",
    )
    args = parser.parse_args(argv)

    try:
        fetch(args.target_os, force=args.force)
    except Exception as exc:
        print(f"Preuzimanje nije uspelo: {exc}", file=sys.stderr)
        if args.allow_system_fallback and copy_system_ffmpeg(args.target_os) is not None:
            return 0
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
