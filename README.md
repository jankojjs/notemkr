# notemkr — MP3 → note za harmoniku

Alat koji iz MP3 snimka pravi notni zapis (MIDI + MusicXML) sa **razdvojenom desnom
rukom (melodija)** i **levom rukom (bas/akordi)** — kao pomoć profesoru harmonike pri
ručnom "skidanju" pesama na sluh.

> Ovo je **pomoć/nacrt**, ne savršena transkripcija. Polifonija i brzi pasaži su najteži.

## Status
Repo je u izradi (orkestrirani build kroz VibeTerm). Pun scaffold i pipeline dolaze kroz
taskove 1–9.

## Cilj arhitekture (pregled)
```
MP3 → dekodiranje → basic-pitch (note) → kvantizacija+tonalitet →
      razdvajanje ruku (desna/leva) → izvoz (MIDI/MusicXML/PDF)
      → lokalni web server (drag-drop) → prikaz nota u browseru
```

## Pokretanje
Biće dopunjeno kroz Task 1 (scaffold) i Task 8 (pakovanje za Windows).
