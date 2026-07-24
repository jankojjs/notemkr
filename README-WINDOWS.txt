notemkr — iz snimka pravi note
==============================

Sta je ovo
----------
Program koji iz snimka pesme (MP3) napravi note za harmoniku, razdvojene na
desnu ruku (melodija) i levu ruku (bas i akordi). Note se vide na ekranu, a mogu
da se preuzmu kao MIDI ili kao notni zapis (MusicXML) za Sibelius/MuseScore.


Kako se pokrece
---------------
1. Raspakuj ovaj ZIP negde gde ti je zgodno (npr. na Desktop).

2. Udji u folder "notemkr" i dupli klik na "notemkr.exe".
   (Ako si preuzeo verziju sa jednim fajlom, dupli klik na "notemkr.exe" direktno.)

3. Otvorice se crni prozor sa tekstom, a odmah zatim i internet pretrazivac
   (Chrome/Edge) sa stranicom programa.

   >>> CRNI PROZOR MORA DA OSTANE OTVOREN dok radis. <<<
       On je sam program. Kada zavrsis, samo ga zatvori.

4. Na stranici prevuci MP3 (ili klikni i izaberi fajl sa racunara).
   Sacekaj — obrada traje otprilike koliko i sama pesma, ponekad i duze.

5. Kada zavrsi, vide se tempo, tonalitet i note, i dugmad za preuzimanje.


Prvo pokretanje
---------------
Prvi put moze da potraje 10-60 sekundi dok se program "razbudi" — to je normalno.
Windows ume da prikaze plavi prozor "Windows protected your PC" (SmartScreen),
jer program nije placeno digitalno potpisan. Klikni "More info" pa "Run anyway".
Ako se javi Windows Firewall, dovoljno je "Cancel" / "Allow access" — svejedno je,
program ne izlazi na internet.


Vazno
-----
* Ne treba ti internet. Sve se racuna na tvom racunaru i nista se nigde ne salje.
* Ne treba ti Python ni bilo kakva instalacija.
* Ako si preuzeo verziju sa folderom: ne izvlaci "notemkr.exe" iz foldera —
  program koristi ostale fajlove pored sebe.


Ako nesto ne radi
-----------------
* Stranica se ne otvori sama:
  otvori pretrazivac i ukucaj adresu koja pise u crnom prozoru
  (obicno http://127.0.0.1:8000/).

* Pise da je port zauzet:
  program sam prelazi na sledeci slobodan port — pogledaj adresu u crnom prozoru.

* Crni prozor se odmah zatvori:
  otvori "Command Prompt", prevuci notemkr.exe u njega i pritisni Enter —
  tako ce poruka o gresci ostati na ekranu.

* Snimak se ne ucitava:
  probaj da ga prvo prebacis u MP3 format.


Sta je jos u paketu
-------------------
Uz program idu i gotovi delovi drugih autora:
* ffmpeg (za citanje MP3-a)          — LGPL, https://ffmpeg.org
* basic-pitch model (Spotify)        — Apache 2.0
* OpenSheetMusicDisplay (prikaz nota) — BSD-3


Napomena o rezultatu
--------------------
Ovo je pomoc pri "skidanju" pesme na sluh, a ne savrsena transkripcija.
Brzi pasazi i vise nota odjednom su najteži deo i tu greske ocekuj — note
sluze kao nacrt koji se dalje doteruje u Sibelius-u ili MuseScore-u.
