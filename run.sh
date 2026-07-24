#!/usr/bin/env bash
# notemkr — pokretanje na macOS-u / Linux-u.
#
#     ./run.sh                 pokreni aplikaciju (otvara se browser)
#     ./run.sh --port 8010     drugi port
#     ./run.sh --no-browser    bez otvaranja browsera
#
# Prvi put skripta napravi virtuelno okruzenje (.venv) i instalira zavisnosti —
# to traje par minuta i jedino tada treba internet. Svako sledece pokretanje je
# trenutno i radi offline.
#
# Na Mac-u se moze i duplo kliknuti: napravi kopiju sa nastavkom .command
#     cp run.sh run.command && chmod +x run.command
# (Finder pokrece .command fajlove u Terminalu.)

set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
PYTHON="${PYTHON:-python3}"
BASIC_PITCH_VERSION="0.4.0"

# `notemkr` konzolna skripta je znak da je okruzenje vec spremno.
if [ ! -x "$VENV/bin/notemkr" ]; then
  echo "== Prvo pokretanje: pripremam okruzenje (treba internet, par minuta) =="

  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Greska: '$PYTHON' nije nadjen. Instaliraj Python 3.11+ (brew install python)." >&2
    exit 1
  fi

  [ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -e .
  # basic-pitch trazi TensorFlow u metapodacima, a nama treba samo ONNX (vidi README).
  "$VENV/bin/pip" install --no-deps "basic-pitch==$BASIC_PITCH_VERSION"

  echo "== Okruzenje je spremno =="
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Napomena: 'ffmpeg' nije u PATH-u — MP3 snimci se mozda nece ucitati."
  echo "          Instalacija: brew install ffmpeg"
fi

exec "$VENV/bin/python" -m notemkr.launcher "$@"
