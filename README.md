# notemkr — MP3 → note za harmoniku

Alat koji iz MP3 snimka pravi notni zapis (MIDI + MusicXML) sa **razdvojenom desnom
rukom (melodija)** i **levom rukom (bas/akordi)** — kao pomoć profesoru harmonike pri
ručnom "skidanju" pesama na sluh.

> Ovo je **pomoć/nacrt**, ne savršena transkripcija. Polifonija i brzi pasaži su najteži.

## Status
Pipeline radi od MP3-a do notnog zapisa: dekodiranje → prepoznavanje nota →
tempo/kvantizacija/tonalitet → razdvajanje ruku → izvoz MIDI/MusicXML (+ PDF).
Preostaje web sloj (drag-drop upload i prikaz u browseru).

## Arhitektura pipeline-a
```
MP3 → dekodiranje (audio.py)
    → basic-pitch note (transcribe.py)
    → kvantizacija + tempo/tonalitet (quantize.py)
    → razdvajanje ruku: desna/leva (split_hands.py)
    → izvoz MIDI / MusicXML / PDF (export.py)
    → lokalni web server, drag-drop (server.py) → prikaz nota u browseru (web/)
```

Glavna ulazna tačka je `notemkr.transcribe_file(path) -> dict`:

```python
{
  "source": "pesma.mp3", "status": "ok", "duration_sec": 9.0,
  "tempo_bpm": 120.19, "key": "G major", "time_signature": "4/4",
  "right_hand": [ {...} ],   # melodija
  "left_hand":  [ {...} ],   # bas i akordi
  "warnings": [],
}
```

Svaka nota je običan `dict` (pa je rezultat direktno JSON-serializabilan):
`pitch`, `start`, `end` (sekunde), `velocity`, `confidence`, plus `start_beat` i
`duration_beats` nakon kvantizacije, `hand` nakon razdvajanja, a note leve ruke i
`role` (`bass`/`chord`) i `chord` (osnovni ton + tip akorda).

## Struktura projekta
```
notemkr/          Python paket
  audio.py        dekodiranje/priprema audia
  notes.py        zajednički format note kroz ceo pipeline
  transcribe.py   glavni pipeline (transcribe_file)
  quantize.py     kvantizacija ritma, tempo, tonalitet
  split_hands.py  razdvajanje leve i desne ruke
  export.py       izvoz MIDI / MusicXML / PDF
  cli.py          komandna linija (notemkr-transcribe)
  server.py       lokalni FastAPI web server
web/              frontend (drag-drop upload, prikaz nota)
samples/          test snimci + generator test snimka
pyproject.toml    metapodaci i zavisnosti
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

## Upotreba

### Komandna linija
```bash
notemkr-transcribe pesma.mp3 -o izlaz/       # ili: python -m notemkr pesma.mp3
```
Ispisuje tempo, tonalitet i broj nota po ruci, a pored snimka (ili u `-o` folderu)
pravi `pesma.mid`, `pesma.musicxml` i — ako je MuseScore dostupan — `pesma.pdf`.

Korisne opcije:

| opcija | značenje |
| --- | --- |
| `--grid 16` | kvantizacija na šesnaestine (podrazumevano osmine) |
| `--split-pitch 62` | pomeri granicu između ruku (MIDI visina, 60 = C4) |
| `--monophonic` | desna ruka kao jedna melodijska linija |
| `--snap-to-scale` | izbaci vanlestvične note niske pouzdanosti |
| `--json` | ispiši ceo rezultat kao JSON |

Na test snimku: **120.19 BPM**, tonalitet **G major**, melodija u desnoj (G4–G5),
bas i akordi (G, C, D) u levoj ruci.

### Iz Python koda
```python
from notemkr import transcribe_file, export_all

result = transcribe_file("pesma.mp3")
files = export_all(result, out_dir="izlaz")
print(result["tempo_bpm"], result["key"], files["musicxml"])
```

Test snimak (`samples/melodija-test.mp3`) je generisan skriptom
`python samples/make_sample.py` — kratak, sintetički, bez autorskih prava.

### Izvoz
- **`.mid`** — dve staze: Track 1 desna ruka (GM Accordion), Track 2 leva (Tango Accordion).
- **`.musicxml`** — partitura sa dva sistema (violinski + bas ključ), sa tempom,
  taktomerom i tonalitetom; otvaraju je i Sibelius i MuseScore.
- **`.pdf`** — opciono, preko MuseScore CLI. Ako MuseScore nije nađen, korak se
  preskače bez greške; putanju možeš zadati kroz `MUSESCORE_PATH`.

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
