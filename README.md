# notemkr — MP3 → note za harmoniku

Alat koji iz MP3 snimka pravi notni zapis (MIDI + MusicXML) sa **razdvojenom desnom
rukom (melodija)** i **levom rukom (bas/akordi)** — kao pomoć profesoru harmonike pri
ručnom "skidanju" pesama na sluh.

> Ovo je **pomoć/nacrt**, ne savršena transkripcija. Polifonija i brzi pasaži su najteži.

## Status
Repo je u izradi (orkestrirani build kroz VibeTerm). Implementirano: dekodiranje audia
i prepoznavanje nota (basic-pitch/ONNX). Kvantizacija, razdvajanje ruku i izvoz dolaze
kroz naredne taskove.

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
Python **3.11–3.13**. Python paketi (opsezi u `pyproject.toml`): basic-pitch (ONNX backend
preko `onnxruntime`, umesto TensorFlow radi lakšeg pakovanja), librosa, pretty_midi,
mido, music21, fastapi, uvicorn, python-multipart.

### Zašto se basic-pitch instalira posebno
`basic-pitch` u svojim metapodacima **tvrdo zahteva TensorFlow** (na Windows-u za
Python ≥ 3.11) odnosno `tensorflow-macos` (na macOS-u za Python > 3.11) — iako mu za rad
sa ONNX modelom TensorFlow uopšte ne treba (backend bira pri uvozu, `try/except`).
Zato se instalira bez zavisnosti, a njegove stvarne runtime zavisnosti (numpy, scipy,
librosa, pretty_midi, resampy, mir_eval) su navedene u `pyproject.toml`:

```bash
pip install --no-deps basic-pitch==0.4.0
```

Rezultat: isti model, ~500 MB manje instalacije, isto ponašanje na Mac-u i Windows-u.

**Runtime zavisnost: `ffmpeg`** — mora biti u PATH-u za dekodiranje MP3/M4A snimaka.
- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg` (ili preuzmi sa ffmpeg.org i dodaj u PATH)

## Instalacija i pokretanje

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install --no-deps basic-pitch==0.4.0
```

### Windows (PowerShell)
```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
pip install --no-deps basic-pitch==0.4.0
```

Cross-platform od starta — bez OS-specifičnih putanja (koristi se `pathlib`).

### Provera
```bash
python -c "
import notemkr
r = notemkr.transcribe_file('samples/melodija-test.mp3')
print(r['status'], r['duration_sec'], 'nota:', len(r['right_hand']) + len(r['left_hand']))"
```

Test snimak (`samples/melodija-test.mp3`) je generisan skriptom
`python samples/make_sample.py` — kratak, sintetički, bez autorskih prava.

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
