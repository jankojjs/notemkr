/* notemkr frontend: prevuci snimak -> POST /transcribe -> prati /status -> prikaži note.
   Sve ide ka lokalnom serveru sa iste adrese; ništa ne odlazi na internet. */

(() => {
  "use strict";

  const PERIOD_ANKETE_MS = 600;
  const NAJVECI_ZUM = 2.0;
  const NAJMANJI_ZUM = 0.5;
  const KORAK_ZUMA = 0.15;
  const SIRINA_PUNOG_ZUMA = 720; // px sadržaja na kojima partitura lepo stane na 100%

  // Faze koje server javlja -> rečenica koju korisnik vidi.
  const FAZE = {
    "cekanje": "Šaljem snimak…",
    "u redu za obradu": "Čeka na obradu…",
    "prepoznavanje nota": "Slušam snimak i prepoznajem note…",
    "izvoz nota": "Ispisujem note…",
    "gotovo": "Gotovo",
  };

  const NAZIVI_TONOVA = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

  const $ = (id) => document.getElementById(id);

  const zona = $("zona");
  const unosFajla = $("fajl");
  const obrada = $("obrada");
  const greska = $("greska");
  const rezultat = $("rezultat");
  const traka = $("traka-punjenje");
  const notniList = $("notni-list");

  let osmd = null;
  let zum = 1.0;
  let uToku = false;

  // --- prikaz sekcija ---------------------------------------------------------

  const prikazi = (element, vidljivo) => { element.hidden = !vidljivo; };

  function pokaziObradu(nazivFajla) {
    document.body.classList.add("radi");
    $("obrada-fajl").textContent = nazivFajla;
    $("obrada-faza").textContent = FAZE["cekanje"];
    traka.style.width = "4%";
    prikazi(obrada, true);
    prikazi(greska, false);
    prikazi(rezultat, false);
  }

  function pokaziGresku(poruka) {
    document.body.classList.remove("radi");
    uToku = false;
    $("greska-tekst").textContent = poruka;
    prikazi(greska, true);
    prikazi(obrada, false);
  }

  function pocetakIznova() {
    document.body.classList.remove("radi");
    uToku = false;
    unosFajla.value = "";
    prikazi(greska, false);
    prikazi(rezultat, false);
    prikazi(obrada, false);
    zona.focus();
  }

  document.querySelectorAll("[data-ponovo]").forEach((dugme) => {
    dugme.addEventListener("click", pocetakIznova);
  });

  // --- izbor snimka -----------------------------------------------------------

  zona.addEventListener("click", () => unosFajla.click());
  unosFajla.addEventListener("change", () => {
    if (unosFajla.files.length) posalji(unosFajla.files[0]);
  });

  ["dragenter", "dragover"].forEach((dogadjaj) => {
    zona.addEventListener(dogadjaj, (e) => {
      e.preventDefault();
      zona.classList.add("uvuci");
    });
  });

  ["dragleave", "dragend", "drop"].forEach((dogadjaj) => {
    zona.addEventListener(dogadjaj, () => zona.classList.remove("uvuci"));
  });

  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    const fajl = e.dataTransfer && e.dataTransfer.files[0];
    if (fajl) posalji(fajl);
  });

  // Bez ovoga browser otvori ispušteni snimak umesto da ga preda stranici.
  ["dragover", "drop"].forEach((dogadjaj) => {
    document.addEventListener(dogadjaj, (e) => {
      if (!zona.contains(e.target)) e.preventDefault();
    });
  });

  // --- podešavanja ------------------------------------------------------------

  const klizacGranice = $("split_pitch");
  const prikazGranice = $("split-prikaz");

  function osveziGranicu() {
    const visina = Number(klizacGranice.value);
    const naziv = NAZIVI_TONOVA[visina % 12] + (Math.floor(visina / 12) - 1);
    prikazGranice.textContent = `${naziv} (${visina})`;
  }

  klizacGranice.addEventListener("input", osveziGranicu);
  osveziGranicu();

  function podesavanja() {
    const forma = new FormData();
    forma.append("grid", $("grid").value);
    forma.append("split_pitch", klizacGranice.value);
    forma.append("monophonic", String($("monophonic").checked));
    forma.append("pdf", String($("pdf").checked));
    forma.append("background", "true");
    return forma;
  }

  // --- slanje i praćenje ------------------------------------------------------

  async function posalji(fajl) {
    if (uToku) return;
    uToku = true;
    pokaziObradu(fajl.name);

    const forma = podesavanja();
    forma.append("file", fajl, fajl.name);

    let odgovor;
    try {
      odgovor = await fetch("transcribe", { method: "POST", body: forma });
    } catch (e) {
      pokaziGresku("Server ne odgovara. Proveri da li je notemkr još uvek pokrenut.");
      return;
    }

    const telo = await procitajJson(odgovor);
    if (!odgovor.ok) {
      pokaziGresku(porukaGreske(telo, odgovor.status));
      return;
    }

    prati(telo.job_id);
  }

  async function prati(jobId) {
    while (uToku) {
      await pauza(PERIOD_ANKETE_MS);

      let stanje;
      try {
        stanje = await procitajJson(await fetch(`status/${jobId}`));
      } catch (e) {
        pokaziGresku("Veza sa serverom je prekinuta.");
        return;
      }

      if (!stanje || !stanje.status) {
        pokaziGresku("Server je vratio neočekivan odgovor.");
        return;
      }

      osveziNapredak(stanje);

      if (stanje.status === "error") {
        pokaziGresku(porukaGreske(stanje));
        return;
      }
      if (stanje.status === "done") {
        const pun = await procitajJson(await fetch(`status/${jobId}?musicxml=true`));
        await pokaziRezultat(pun);
        return;
      }
    }
  }

  function osveziNapredak(stanje) {
    $("obrada-faza").textContent = FAZE[stanje.stage] || stanje.stage;
    traka.style.width = `${Math.max(4, Math.round((stanje.progress || 0) * 100))}%`;
  }

  // --- rezultat ---------------------------------------------------------------

  async function pokaziRezultat(podaci) {
    document.body.classList.remove("radi");
    uToku = false;

    $("tempo").textContent = podaci.tempo_bpm ? `${Math.round(podaci.tempo_bpm)} BPM` : "—";
    $("tonalitet").textContent = podaci.key || "—";
    $("takt").textContent = podaci.time_signature || "—";
    $("note").textContent =
      `D ${podaci.note_counts.right_hand} · L ${podaci.note_counts.left_hand}`;

    postaviPreuzimanje($("preuzmi-midi"), podaci.files.midi);
    postaviPreuzimanje($("preuzmi-musicxml"), podaci.files.musicxml);
    postaviPreuzimanje($("preuzmi-pdf"), podaci.files.pdf);

    const lista = $("upozorenja");
    lista.textContent = "";
    (podaci.warnings || []).forEach((tekst) => {
      const stavka = document.createElement("li");
      stavka.textContent = tekst;
      lista.appendChild(stavka);
    });
    prikazi(lista, (podaci.warnings || []).length > 0);

    prikazi(obrada, false);
    prikazi(rezultat, true);
    rezultat.scrollIntoView({ behavior: "smooth", block: "start" });

    await nacrtajNote(podaci.musicxml);
  }

  function postaviPreuzimanje(veza, putanja) {
    if (!putanja) {
      veza.hidden = true;
      veza.removeAttribute("href");
      return;
    }
    veza.hidden = false;
    veza.href = putanja.replace(/^\//, "");
  }

  async function nacrtajNote(musicxml) {
    if (!musicxml) {
      notniList.textContent = "Nema nota za prikaz — probaj snimak sa jasnijom melodijom.";
      return;
    }

    try {
      if (!osmd) {
        osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(notniList, {
          autoResize: true,
          backend: "svg",
          drawTitle: true,
          drawSubtitle: false, // music21 upisuje naslov i kao podnaslov
          drawPartNames: true,
          drawPartAbbreviations: false, // "Acc" iznad svakog sledećeg sistema samo smeta
          drawingParameters: "default",
          pageFormat: "Endless", // jedan dugačak list umesto praznog dna A4 stranice
        });
      }
      await osmd.load(musicxml);
      postaviZum(pocetniZum(), { iscrtaj: false });
      osmd.zoom = zum;
      osmd.render();
    } catch (e) {
      notniList.textContent = "Note se ne mogu prikazati u browseru, ali fajlovi iznad rade.";
    }
  }

  // --- zum --------------------------------------------------------------------

  // Na uskom ekranu partitura se podrazumevano smanji da stane bez horizontalnog skrola.
  function pocetniZum() {
    const sirina = notniList.clientWidth || SIRINA_PUNOG_ZUMA;
    return Math.min(1, Math.max(NAJMANJI_ZUM, sirina / SIRINA_PUNOG_ZUMA));
  }

  function postaviZum(novi, { iscrtaj = true } = {}) {
    zum = Math.min(NAJVECI_ZUM, Math.max(NAJMANJI_ZUM, novi));
    $("zum-prikaz").textContent = `${Math.round(zum * 100)}%`;
    if (iscrtaj && osmd && osmd.GraphicSheet) {
      osmd.zoom = zum;
      osmd.render();
    }
  }

  $("zum-manje").addEventListener("click", () => postaviZum(zum - KORAK_ZUMA));
  $("zum-vise").addEventListener("click", () => postaviZum(zum + KORAK_ZUMA));

  // --- pomoćne ----------------------------------------------------------------

  const pauza = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function procitajJson(odgovor) {
    try {
      return await odgovor.json();
    } catch (e) {
      return null;
    }
  }

  function porukaGreske(telo, status) {
    if (telo && telo.detail) return String(telo.detail);
    if (telo && telo.error) return String(telo.error);
    if (telo && Array.isArray(telo.warnings) && telo.warnings.length) return telo.warnings.join("\n");
    return `Server je odgovorio greškom${status ? ` (${status})` : ""}.`;
  }
})();
