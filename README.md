# notemkr — MP3 → note za harmoniku

Alat koji iz MP3 snimka pravi notni zapis (MIDI + MusicXML) sa **razdvojenom desnom
rukom (melodija)** i **levom rukom (bas/akordi)** — kao pomoć profesoru harmonike pri
ručnom "skidanju" pesama na sluh.

> Ovo je **pomoć/nacrt**, ne savršena transkripcija. Polifonija i brzi pasaži su najteži.

## Status
Radi ceo put od MP3-a do nota u browseru: dekodiranje → prepoznavanje nota →
tempo/kvantizacija/tonalitet → razdvajanje ruku → izvoz MIDI/MusicXML (+ PDF) →
lokalni server sa drag-drop stranicom i prikazom partiture. Spakovano za Windows
(`.exe`, bez instalacije Python-a) i za Mac (`./run.sh`).

## Za korisnika: Windows, bez instalacije

Nije potreban Python, ffmpeg ni internet — sve je u paketu.

1. **Preuzmi** poslednji `notemkr-windows.zip`:
   *Releases* na GitHub-u, ili *Actions → „Windows build (.exe)" → poslednji uspešan
   run → „Artifacts".
2. **Raspakuj** ZIP (npr. na Desktop).
3. **Dupli klik** na `notemkr\notemkr.exe`.
4. Otvori se crni prozor, a odmah zatim i browser sa stranicom aplikacije.
   **Crni prozor mora da ostane otvoren** dok aplikacija radi — zatvaranje prozora
   je ujedno i gašenje aplikacije.
5. Prevuci MP3 na stranicu → note.

Uz ZIP ide i `README-WINDOWS.txt` sa istim uputstvom, napisan za nekoga ko nikada
nije otvorio terminal (uključujući SmartScreen upozorenje pri prvom pokretanju).

Dve varijante paketa:

| paket | šta je | kada |
| --- | --- | --- |
| `notemkr-windows.zip` | folder sa `notemkr.exe` + `_internal\` | **preporučeno** — startuje odmah |
| `notemkr-windows-jedan-fajl.zip` | jedan `notemkr.exe` (~190 MB) | lakše za slanje; svako pokretanje se raspakuje u temp, pa traje duže |

U verziji sa folderom `notemkr.exe` se ne sme izvlačiti iz foldera — koristi fajlove
pored sebe.

## Za korisnika: macOS

Na Mac-u nema `.exe`-a; koristi se skripta iz korena repoa:

```bash
./run.sh                 # prvi put napravi .venv i instalira zavisnosti (treba internet)
./run.sh --port 8010     # drugi port
```
Svako sledeće pokretanje je trenutno i radi offline. Za pokretanje duplim klikom iz
Finder-a: `cp run.sh run.command && chmod +x run.command`.

Isto to ručno, ako `.venv` već postoji: `.venv/bin/python -m notemkr.launcher`.

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
  server.py       lokalni FastAPI web server (/transcribe, /download)
  launcher.py     ulazna tačka spakovane aplikacije (port, browser, poruke)
  runtime.py      gde su fajlovi — iz izvornog koda i iz .exe paketa
web/              frontend (drag-drop upload, prikaz nota)
  index.html      stranica
  styles.css      izgled
  app.js          upload, praćenje obrade, prikaz partiture
  vendor/         OpenSheetMusicDisplay (lokalno, bez CDN-a)
packaging/        pakovanje u .exe
  notemkr.spec    PyInstaller recept (Windows + Mac, onedir/onefile)
  notemkr_app.py  skripta koju PyInstaller pretvara u izvršni fajl
  fetch_ffmpeg.py preuzimanje statičkog ffmpeg-a u vendor/
  smoke_test.py   provera gotovog paketa (pokreni ga i propusti snimak)
  build.sh        gradnja na Mac-u/Linux-u
  build_windows.ps1  gradnja na Windows mašini
.github/workflows/build-windows.yml   CI koji pravi .exe (jedini pravi izvor .exe-a)
samples/          test snimci + generator test snimka
jobs/             rezultati obrade po poslu (pravi se sam, van gita)
run.sh            pokretanje na Mac-u/Linux-u (napravi .venv pri prvom pokretanju)
README-WINDOWS.txt  uputstvo koje ide uz Windows ZIP
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
- Windows: **ne treba ništa** — `ffmpeg.exe` je unutar `.exe` paketa (vidi
  [Pakovanje](#pakovanje-kako-nastaje-exe)). Za rad iz izvornog koda:
  `winget install Gyan.FFmpeg` (ili preuzmi sa ffmpeg.org i dodaj u PATH)

## Instalacija i pokretanje

Za samo korišćenje aplikacije ovo nije potrebno: na Windows-u postoji gotov `.exe`,
na Mac-u `./run.sh` (obe varijante su opisane gore). Ovde je ručna instalacija za
rad na kodu.

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

### Web (drag-drop u browseru)
```bash
notemkr                          # ili: python -m notemkr.server
python -m notemkr.launcher       # isto, ali kao spakovana verzija (sam nađe port)
```
Server sluša na `http://127.0.0.1:8000/` i sam otvara browser (`--no-browser` da ne
otvara). Opcije: `--host`, `--port`, `--jobs-dir`.

Na stranici prevučeš snimak (ili klikneš i izabereš ga), vidiš napredak, a zatim
tempo, tonalitet, note u browseru i dugmad za preuzimanje MIDI/MusicXML/PDF-a.
Note crta **OpenSheetMusicDisplay**, koji stoji lokalno u `web/vendor/` — bez CDN-a,
pa stranica radi i bez interneta.

Sve je lokalno: server sluša samo na `127.0.0.1`, snimak se obradi na tvom računaru
i nigde se ne šalje. Rezultati stoje u `jobs/<job_id>/` i brišu se pri sledećem
pokretanju servera (i kad se nakupi više od `NOTEMKR_MAX_JOBS` poslova).

#### API
| ruta | šta radi |
| --- | --- |
| `POST /transcribe` | multipart upload (`file`) → pokreće pipeline, vraća JSON |
| `GET /status/{job_id}` | stanje posla (`?musicxml=true` vraća i partituru) |
| `GET /download/{job_id}/{tip}` | preuzimanje: `midi`, `musicxml`, `pdf` |
| `GET /health` | provera servera (ima li `ffmpeg`, ima li MuseScore) |

```bash
curl -F file=@samples/melodija-test.mp3 http://127.0.0.1:8000/transcribe
```
```json
{
  "job_id": "4e93d39a…", "status": "done", "filename": "melodija-test.mp3",
  "tempo_bpm": 120.19, "key": "G major", "time_signature": "4/4",
  "note_counts": { "right_hand": 15, "left_hand": 27 },
  "right_hand": [ {...} ], "left_hand": [ {...} ], "warnings": [],
  "files": { "midi": "/download/4e93d39a…/midi",
             "musicxml": "/download/4e93d39a…/musicxml", "pdf": null },
  "musicxml": "<?xml version=\"1.0\"…"
}
```

Uz obrazac forme idu i podešavanja: `grid` (4/8/16), `split_pitch`, `monophonic`,
`snap_to_scale`, `quantize`, `pdf`. Uz `background=true` odgovor stiže odmah (202),
a napredak se prati preko `/status/{job_id}` — tako radi i sama stranica.

Podešavanja kroz okruženje: `NOTEMKR_JOBS_DIR`, `NOTEMKR_MAX_UPLOAD_MB` (50),
`NOTEMKR_MAX_JOBS` (20), `NOTEMKR_HOST`, `NOTEMKR_PORT`.

## Pakovanje (kako nastaje .exe)

Recept je `packaging/notemkr.spec` — isti fajl gradi i Windows i Mac verziju.
Ulazna tačka paketa je `notemkr/launcher.py`: nađe slobodan port (ako je 8000
zauzet), sačeka da server *stvarno* proradi pa tek onda otvori browser, i pri
grešci zadrži prozor otvoren da se poruka pročita.

### Windows .exe se gradi na Windows-u
PyInstaller **ne radi cross-build**: `.exe` se ne može napraviti sa Mac-a. Zato je
pravi izvor `.exe`-a GitHub Actions workflow `.github/workflows/build-windows.yml`
(`windows-latest`, Python 3.11). On radi sve korake sam — instalira zavisnosti,
proverava da TensorFlow *nije* ušao, preuzme statički `ffmpeg.exe`, pusti
PyInstaller u oba režima (`onedir` i `onefile`), pokrene smoke test nad gotovim
paketom i okači rezultat kao artifact. Na tag `v*` pravi i GitHub Release.

Ručno pokretanje: *Actions → „Windows build (.exe)" → „Run workflow"*.

Na samoj Windows mašini: `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`.

### Mac / Linux
```bash
packaging/build.sh                    # dist/notemkr/  (folder)
NOTEMKR_ONEFILE=1 packaging/build.sh  # dist/notemkr   (jedan fajl)
```

### Provera gotovog paketa
```bash
python packaging/smoke_test.py --dist dist --mode onedir
```
Pokreće spakovanu aplikaciju i propušta pravi snimak kroz nju: `/health` mora da
javi da je `ffmpeg` nađen, `/` da posluži frontend, a `/transcribe` da vrati note.
To je test prihvatanja nad *paketom*, a ne nad izvornim kodom.

### Šta ulazi u paket i zašto
| stavka | zašto |
| --- | --- |
| `web/` (sa vendorovanim OSMD-om) | stranica i prikaz nota rade bez CDN-a |
| `basic_pitch/saved_models/.../nmp.onnx` | model uz aplikaciju — inače bi trebao internet |
| `onnxruntime` | jedini backend koji basic-pitch ovde koristi |
| `music21`, `librosa`, `resampy`, `mir_eval` | nose svoje data fajlove pored `.py`-a |
| `bin/ffmpeg[.exe]` | dekodiranje MP3-a na mašini koja nema ffmpeg |
| ~~TensorFlow~~ | **isključen**: basic-pitch ga traži u metapodacima, a nikad ga ne uveze uz ONNX backend (uštedi ~500 MB) |

`ffmpeg` se ne drži u gitu — preuzima ga `packaging/fetch_ffmpeg.py` u
`packaging/vendor/<os>/`. To je jedini korak kome treba internet, i to samo pri
gradnji. Za Windows se uzima **statički LGPL** build (BtbN, tag `latest`; gyan.dev
kao rezerva jer ume da vrati 503) — LGPL varijanta nema GPL-only delove koji nam za
dekodiranje MP3-a ionako ne trebaju, pa je deljenje gotovog paketa jednostavnije.

### Gde aplikacija piše
Spakovana aplikacija ne piše pored `.exe`-a (tamo često nema prava), nego u
korisnički folder: `%LOCALAPPDATA%\notemkr\jobs` na Windows-u,
`~/Library/Application Support/notemkr/jobs` na Mac-u. Iz izvornog koda ostaje
`jobs/` u korenu repoa, kao i do sada. Sve to rešava `notemkr/runtime.py` — nijedan
modul ne sme da računa putanje preko `__file__`, jer u paketu tih foldera nema.

### Offline
Provereno: sa praznim PATH-om (bez sistemskog `ffmpeg`-a) i bez izlaza na internet,
spakovana aplikacija podigne server, posluži stranicu i iz `samples/melodija-test.mp3`
izvuče note (120.19 BPM, G major) — isto kao iz izvornog koda.

## Razvoj
```bash
pip install -e ".[dev]"
pytest
```
