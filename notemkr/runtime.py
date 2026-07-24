"""Gde aplikacija nalazi svoje fajlove — iz izvornog koda i iz spakovane (.exe) verzije.

Kada PyInstaller spakuje aplikaciju, `notemkr/` vise nije folder na disku: kod se
izvrsava iz jednog izvrsnog fajla, a prilozeni resursi (frontend iz `web/`, model,
`ffmpeg`) zive u privremenom folderu na koji pokazuje `sys._MEIPASS`. Zato nijedan
modul ne sme da racuna putanje preko `__file__`; sve ide kroz funkcije odavde.

Razlika koju modul pravi:

* **resursi** (`web/`, `bin/`) — samo za citanje, unutar paketa (`bundle_dir`);
* **podaci** (folder `jobs/`) — mora da bude upisiv, pa iz .exe-a ide u korisnicki
  folder (`%LOCALAPPDATA%` / `~/Library/Application Support`), a ne pored .exe-a
  koji lako zavrsi u `Program Files` ili u privremenom folderu (`default_jobs_dir`).

`prepare_runtime()` se poziva na startu svake ulazne tacke (launcher, server, CLI) i
ubacuje prilozeni `ffmpeg` u PATH — bez toga dekodiranje MP3-a ne radi na masini
koja nema instaliran ffmpeg.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "notemkr"

# Nazivi podfoldera unutar paketa (moraju da se poklope sa `packaging/notemkr.spec`).
WEB_SUBDIR = "web"
BIN_SUBDIR = "bin"

# Alati koje prilazemo uz aplikaciju (Windows build; na Mac-u se koristi sistemski).
FFMPEG_NAMES = ("ffmpeg.exe", "ffmpeg")


def is_frozen() -> bool:
    """Da li kod radi iz PyInstaller paketa (a ne iz izvornog stabla)."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Koren prilozenih resursa: `sys._MEIPASS` u paketu, koren repoa u razvoju."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """Folder u kome aplikacija fizicki stoji (pored .exe-a) — za poruke korisniku."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return bundle_dir()


def web_dir() -> Path:
    """Folder sa frontend-om (`index.html`, `app.js`, `vendor/`)."""
    return bundle_dir() / WEB_SUBDIR


def bin_dir() -> Path:
    """Folder sa prilozenim binarnim alatima (`ffmpeg`)."""
    return bundle_dir() / BIN_SUBDIR


def user_data_dir() -> Path:
    """Folder za podatke aplikacije, po pravilima svakog OS-a.

    Windows: `%LOCALAPPDATA%\\notemkr`, macOS: `~/Library/Application Support/notemkr`,
    ostalo: `$XDG_DATA_HOME/notemkr` (podrazumevano `~/.local/share/notemkr`).
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "~"
    elif sys.platform == "darwin":
        base = "~/Library/Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return Path(base).expanduser() / APP_NAME


def default_jobs_dir() -> Path:
    """Podrazumevani folder za rezultate obrade.

    U razvoju je to `jobs/` u korenu repoa (kao i do sada), a iz spakovane aplikacije
    korisnicki folder — jedino mesto na koje sme da se pise bez obzira gde .exe stoji.
    """
    if is_frozen():
        return user_data_dir() / "jobs"
    return bundle_dir() / "jobs"


def bundled_ffmpeg() -> Path | None:
    """Putanja do prilozenog `ffmpeg`-a, ako je spakovan uz aplikaciju."""
    for name in FFMPEG_NAMES:
        candidate = bin_dir() / name
        if candidate.is_file():
            return candidate
    return None


def prepare_runtime() -> None:
    """Pripremi okruzenje za pokretanje; bezbedno je pozvati vise puta.

    Prilozeni `bin/` ide na *pocetak* PATH-a, pa `shutil.which("ffmpeg")` (i librosa
    preko audioread-a) nadju nas ffmpeg i na masini koja ga nema instaliranog. Ako
    ga korisnik ipak ima, nas ide prvi — tako je ponasanje isto na svakoj masini.
    """
    tools = bin_dir()
    if tools.is_dir():
        path = os.environ.get("PATH", "")
        entries = path.split(os.pathsep) if path else []
        if not entries or Path(entries[0]) != tools:
            os.environ["PATH"] = os.pathsep.join([str(tools), *entries]) if entries else str(tools)

    if is_frozen():
        # music21 i librosa povlace matplotlib; bez ekrana/Tk-a jedini siguran
        # backend je Agg (crtanje ionako ne koristimo).
        os.environ.setdefault("MPLBACKEND", "Agg")
