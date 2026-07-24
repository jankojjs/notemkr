# notemkr — MP3 → note za harmoniku

Alat koji iz MP3 snimka pravi notni zapis (MIDI + MusicXML) sa **razdvojenom desnom
rukom (melodija)** i **levom rukom (bas/akordi)** — kao pomoć profesoru harmonike pri
ručnom "skidanju" pesama na sluh.

> Ovo je **pomoć/nacrt**, ne savršena transkripcija. Polifonija i brzi pasaži su najteži.

## Status
Repo je u izradi (orkestrirani build kroz VibeTerm). Ovaj task (1) postavlja scaffold:
strukturu paketa, pinovane zavisnosti i prazan pipeline stub. Prave faze dolaze kroz
taskove 2–9.

## Arhitektura pipeline-a
```
MP3 → dekodiranje (audio.py)
    → basic-pitch note (transcribe.py)
    → kvantizacija + tempo/tonalitet (quantize.py)
    → razdvajanje ruku: desna/leva (split_hands.py)
    → izvoz MIDI / MusicXML (export.py)
    → lokalni web server, drag-drop (server.py) → prikaz nota u browseru (web/)
```

Glavna ulazna tacka je `notemkr.transcribe_file(path) -> dict`. U scaffold-u je stub
koji vraca validno strukturiranu (praznu) rezultat-mapu.

## Struktura projekta
```
notemkr/          Python paket
  audio.py        dekodiranje/priprema audia
  transcribe.py   glavni pipeline (transcribe_file)
  quantize.py     kvantizacija ritma, tempo, tonalitet
  split_hands.py  razdvajanje leve i desne ruke
  export.py       izvoz MIDI / MusicXML
  server.py       lokalni FastAPI web server
web/              frontend (drag-drop upload, prikaz nota)
samples/          test snimci
pyproject.toml    metapodaci i pinovane zavisnosti
```

## Zavisnosti
Python **3.11+**. Python paketi (pinovani u `pyproject.toml`): basic-pitch (ONNX backend
preko `onnxruntime`, umesto TensorFlow radi lakšeg pakovanja), librosa, pretty_midi,
mido, music21, fastapi, uvicorn, python-multipart.

**Runtime zavisnost: `ffmpeg`** — mora biti u PATH-u za dekodiranje MP3/M4A snimaka.
- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg` (ili preuzmi sa ffmpeg.org i dodaj u PATH)

## Instalacija i pokretanje

### macOS / Linux
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows (PowerShell)
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

Cross-platform od starta — bez OS-specifičnih putanja (koristi se `pathlib`).

### Provera scaffold-a
```bash
python -c "import notemkr; print(notemkr.transcribe_file('samples/primer.mp3'))"
```
Ispisuje stub rezultat-mapu (bez čitanja fajla i bez teških zavisnosti).

### Pokretanje web servera (health check)
```bash
notemkr            # ili: python -m notemkr.server
# zatim otvori http://127.0.0.1:8000/health
```

## Razvoj
```bash
pip install -e ".[dev]"
pytest
```
