# PyInstaller spec za notemkr — isti fajl gradi Windows .exe i macOS build.
#
#     pyinstaller packaging/notemkr.spec --noconfirm
#
# Sta ulazi u paket i zasto:
#
#   web/                     frontend + vendorovani OpenSheetMusicDisplay (offline)
#   basic_pitch/saved_models ONNX model (nmp.onnx) — inace bi app trazila model na netu
#   music21/librosa data     ovi paketi nose svoje fajlove pored .py-a
#   bin/ffmpeg[.exe]         dekoder MP3-a, ako je preuzet u packaging/vendor/<os>/
#
# TensorFlow se NAMERNO iskljucuje: basic-pitch ga trazi u metapodacima, ali sa ONNX
# backend-om nikad ne biva uvezen (vidi README). Da udje, paket bi bio ~500 MB veci.
#
# Rezim gradnje bira promenljiva okruzenja NOTEMKR_ONEFILE:
#   (nepostavljena)  -> onedir: folder `dist/notemkr/` sa `notemkr.exe` (brz start)
#   =1               -> onefile: jedan `dist/notemkr.exe` (sporiji start, lakse deljenje)

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

SPEC_DIR = Path(SPECPATH).resolve()  # noqa: F821 - SPECPATH ubacuje PyInstaller
ROOT = SPEC_DIR.parent

ONEFILE = os.environ.get("NOTEMKR_ONEFILE", "").strip().lower() in ("1", "true", "yes")

# Podfolder sa prilozenim ffmpeg-om, po platformi (vidi packaging/fetch_ffmpeg.py).
VENDOR_DIRS = {"win32": "windows", "darwin": "macos"}
VENDOR_DIR = SPEC_DIR / "vendor" / VENDOR_DIRS.get(sys.platform, "linux")

# --- Resursi -------------------------------------------------------------------------

# Frontend ide u paket pod istim imenom foldera koje ocekuje `notemkr.runtime.web_dir`.
datas = [(str(ROOT / "web"), "web")]
binaries = []
hiddenimports = ["notemkr.launcher", "notemkr.server"]

# `collect_all` pokupi i .py module i podatke i dinamicke biblioteke paketa. Ovi paketi
# se uvoze lenjivo (unutar funkcija) ili preko `lazy_loader`-a, pa ih staticka analiza
# PyInstaller-a sama ne bi nasla.
COLLECT_PACKAGES = (
    "basic_pitch",  # + saved_models/icassp_2022/nmp.onnx
    "onnxruntime",
    "librosa",
    "music21",  # nosi svoje data fajlove (corpus, tabele)
    "pretty_midi",
    "mido",
    "resampy",  # .npz filtri za resampling
    "mir_eval",
    "soundfile",
    "soxr",
    "audioread",
    "lazy_loader",
    "uvicorn",  # protokoli/loops se uvoze po imenu, u runtime-u
    "fastapi",
    "multipart",  # python-multipart: upload forme
)

for package in COLLECT_PACKAGES:
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# Neki paketi u runtime-u citaju svoju verziju kroz importlib.metadata; bez kopiranih
# metapodataka to puca tek pri obradi snimka, a ne pri pokretanju.
for distribution in ("librosa", "basic-pitch", "pretty_midi", "music21", "soundfile", "numpy"):
    try:
        datas += copy_metadata(distribution)
    except Exception as exc:  # paket nije instaliran — nije fatalno
        print(f"[notemkr.spec] preskacem metapodatke za {distribution}: {exc}")

# --- Prilozeni ffmpeg ----------------------------------------------------------------

if VENDOR_DIR.is_dir():
    tools = [entry for entry in sorted(VENDOR_DIR.iterdir()) if entry.is_file()]
    binaries += [(str(entry), "bin") for entry in tools]
    print(f"[notemkr.spec] prilazem alate iz {VENDOR_DIR}: {[e.name for e in tools]}")
else:
    print(
        f"[notemkr.spec] UPOZORENJE: nema {VENDOR_DIR} — ffmpeg nece biti u paketu.\n"
        f"[notemkr.spec] Pokreni prvo: python packaging/fetch_ffmpeg.py"
    )

# --- Sta ne treba u paketu -----------------------------------------------------------

excludes = [
    "tensorflow",  # basic-pitch ga trazi u metapodacima, ali koristi ONNX
    "tensorflow_hub",
    "tflite_runtime",
    "coremltools",
    "torch",
    "tkinter",  # matplotlib bez ekrana radi na Agg backend-u (vidi runtime.py)
    "pytest",
    "IPython",
    "notebook",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
]

# --- Gradnja -------------------------------------------------------------------------

analysis = Analysis(  # noqa: F821 - PyInstaller ubacuje ove klase
    [str(SPEC_DIR / "notemkr_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)  # noqa: F821

# `console=True` je namerno: crni prozor je jedini nacin da netehnicki korisnik vidi
# da app radi i da je zaustavi (zatvaranjem prozora).
exe_kwargs = dict(
    name="notemkr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX cesto lazno alarmira antiviruse na Windows-u
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SPEC_DIR / "notemkr.ico") if (SPEC_DIR / "notemkr.ico").is_file() else None,
)

if ONEFILE:
    exe = EXE(  # noqa: F821
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        runtime_tmpdir=None,
        **exe_kwargs,
    )
else:
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, **exe_kwargs)  # noqa: F821
    coll = COLLECT(  # noqa: F821
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="notemkr",
    )
