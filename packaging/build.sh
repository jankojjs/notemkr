#!/usr/bin/env bash
# Napravi spakovanu notemkr aplikaciju na macOS-u / Linux-u.
#
#     packaging/build.sh                 -> dist/notemkr/ (folder, brz start)
#     NOTEMKR_ONEFILE=1 packaging/build.sh   -> dist/notemkr (jedan fajl)
#
# Windows .exe se NE moze napraviti odavde — PyInstaller ne radi cross-build.
# Za njega postoji `packaging/build_windows.ps1` (na Windows masini) ili
# GitHub Actions workflow `.github/workflows/build-windows.yml`.

set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"
PYTHON="${PYTHON:-python3}"

if [ ! -d "$VENV" ]; then
  echo "== Pravim okruzenje za gradnju =="
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install --no-deps "basic-pitch==0.4.0"
fi

"$VENV/bin/pip" install -e ".[build]"

echo "== Preuzimam ffmpeg (ako ga vec nema) =="
"$VENV/bin/python" packaging/fetch_ffmpeg.py --allow-system-fallback || true

echo "== PyInstaller =="
rm -rf build dist
"$VENV/bin/pyinstaller" packaging/notemkr.spec --noconfirm --distpath dist --workpath build

echo
echo "== Gotovo =="
ls -la dist
