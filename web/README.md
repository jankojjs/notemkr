# web/ — frontend

Statična stranica koju poslužuje `notemkr.server`: prevučeš MP3, pratiš obradu i
dobiješ note u browseru + dugmad za preuzimanje.

```
index.html   struktura stranice
styles.css   izgled (svetla i tamna tema)
app.js       upload, praćenje obrade preko /status, prikaz partiture
vendor/      OpenSheetMusicDisplay 2.1.0 (BSD-3-Clause), lokalno
```

Nema build koraka i nema poziva ka internetu — ni fontovi (sistemski), ni ikonica
(ugrađena kao data URI), ni OpenSheetMusicDisplay (stoji u `vendor/`). To je uslov
da alat radi offline i da se kasnije spakuje kao lokalni program.

Novu verziju OpenSheetMusicDisplay-a uzmi iz npm paketa i prekopiraj
`build/opensheetmusicdisplay.min.js` (uz `LICENSE`) u `vendor/`.
