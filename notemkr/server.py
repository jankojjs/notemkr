"""Lokalni web server (FastAPI): upload snimka -> ceo pipeline -> fajlovi + note.

Server je namerno **lokalan**: slusa na 127.0.0.1, snimci se obradjuju na masini
korisnika i nista se ne salje na internet. Rezultati zive u `jobs/<job_id>/`.

Rute:

    POST /transcribe            multipart upload -> pokrece Taskove 2-5, vraca JSON
                                (job_id, note, MusicXML sadrzaj, linkovi za preuzimanje)
    GET  /status/{job_id}       stanje posla (za `background=true` upload)
    GET  /download/{job_id}/{tip}   tip: midi | musicxml | pdf
    GET  /health                health check
    GET  /                      staticki frontend iz `web/`

Obrada je podrazumevano sinhrona (klijent ceka odgovor uz spinner), ali se pusta u
thread pool-u da event loop ostane ziv; uz `background=true` odgovor stize odmah
(202) a napredak se prati preko `/status/{job_id}`.

Teske zavisnosti (fastapi, uvicorn, pa i sam pipeline) uvoze se lenjivo unutar
funkcija, da `import notemkr.server` ostane lagan i da testovi mogu da podmene
pipeline.
"""

# NAPOMENA: ovaj modul namerno *nema* `from __future__ import annotations`. FastAPI
# resava anotacije ruta preko globala modula, a `UploadFile`/`Form` se ovde uvoze
# lenjivo (unutar `create_app`) — sa odlozenim anotacijama ostali bi nerazresivi
# tekstualni forward-ref-ovi. Sve anotacije u ovom fajlu rade na Python 3.11+.

import argparse
import os
import re
import shutil
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from .quantize import DEFAULT_GRID
from .runtime import bundle_dir, default_jobs_dir, web_dir
from .split_hands import DEFAULT_SPLIT_PITCH, HandSplitParams
from .transcribe import TranscriptionParams

# --- Podesavanja ---------------------------------------------------------------------

# Putanje idu preko `notemkr.runtime`, a ne preko `__file__`: u PyInstaller paketu
# `web/` nije pored ovog modula, a `jobs/` mora da zavrsi na upisivom mestu.
REPO_ROOT = bundle_dir()

# Koren frontend foldera i podrazumevani folder za rezultate poslova.
WEB_DIR = web_dir()
DEFAULT_JOBS_DIR = default_jobs_dir()

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# Formati koje dekoder (librosa + ffmpeg) ume da procita.
ALLOWED_SUFFIXES = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".aif", ".aiff")

DEFAULT_MAX_UPLOAD_MB = 50
DEFAULT_MAX_JOBS = 20  # koliko poslova cuvamo na disku pre brisanja najstarijih
UPLOAD_CHUNK_BYTES = 1024 * 1024

# job_id je uvek uuid4 heksadekadno — provera stiti /download i /status od
# putanja tipa "../../etc/passwd".
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# tip preuzimanja -> (kljuc u `export_all`, ekstenzija, MIME)
DOWNLOAD_KINDS: dict[str, tuple[str, str, str]] = {
    "midi": ("midi", ".mid", "audio/midi"),
    "musicxml": ("musicxml", ".musicxml", "application/vnd.recordare.musicxml+xml"),
    "pdf": ("pdf", ".pdf", "application/pdf"),
}

GRID_CHOICES = (4, 8, 16)
MIN_SPLIT_PITCH, MAX_SPLIT_PITCH = 21, 108  # A0 .. C8

# U nazivu fajla drzimo samo slova, cifre, tacku, crticu i razmak — isti skup je
# bezbedan i na Windows-u i na macOS-u.
_UNSAFE_NAME_CHARS = re.compile(r"[^\w.\- ]", re.UNICODE)
MAX_STEM_LENGTH = 60


class UploadError(ValueError):
    """Upload nije prihvatljiv (prazan, prevelik ili nepodrzan format)."""


# --- Poslovi -------------------------------------------------------------------------


@dataclass(slots=True)
class Job:
    """Jedan posao transkripcije: ulazni snimak, stanje obrade i izlazni fajlovi."""

    id: str
    filename: str  # originalni naziv, onakav kakav je korisnik poslao
    stem: str  # ociscen naziv bez ekstenzije (koristi se za izlazne fajlove)
    directory: Path
    input_path: Path
    params: TranscriptionParams
    with_pdf: bool = True
    status: str = "queued"  # queued | running | done | error
    stage: str = "cekanje"  # citljiv opis koraka, za spinner na frontendu
    progress: float = 0.0  # 0..1
    created_at: float = field(default_factory=time.time)
    error: str | None = None
    result: dict[str, Any] | None = None
    files: dict[str, Path | None] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")


class JobStore:
    """Registar poslova u memoriji + njihovi folderi na disku.

    Registar je namerno u memoriji: posle restarta servera stari poslovi vise nisu
    dohvatljivi, pa se njihovi folderi brisu (snimci ne ostaju da leze bez potrebe).
    """

    def __init__(self, root: str | Path, max_jobs: int = DEFAULT_MAX_JOBS) -> None:
        self.root = Path(root).expanduser()
        self.max_jobs = max(1, int(max_jobs))
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(
        self,
        filename: str,
        params: TranscriptionParams,
        with_pdf: bool = True,
    ) -> Job:
        """Napravi posao i njegov folder na disku."""
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir(parents=True, exist_ok=True)

        stem = safe_stem(filename)
        job = Job(
            id=job_id,
            filename=Path(filename or "").name or "snimak",
            stem=stem,
            directory=directory,
            input_path=directory / f"{stem}{safe_suffix(filename)}",
            params=params,
            with_pdf=with_pdf,
        )
        with self._lock:
            self._jobs[job_id] = job
        self._prune()
        return job

    def get(self, job_id: str) -> Job | None:
        """Posao po id-u; nevalidan id nikada ne dodiruje disk."""
        if not JOB_ID_RE.match(job_id or ""):
            return None
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: Job, **fields: Any) -> Job:
        """Atomicno azuriraj polja posla (poziva se iz radne niti)."""
        with self._lock:
            for name, value in fields.items():
                setattr(job, name, value)
        return job

    def remove(self, job: Job) -> None:
        """Zaboravi posao i obrisi njegov folder."""
        with self._lock:
            self._jobs.pop(job.id, None)
        _remove_job_dir(self.root, job.directory)

    def cleanup_orphans(self) -> None:
        """Obrisi foldere poslova zaostale od ranijeg pokretanja servera."""
        if not self.root.is_dir():
            return
        with self._lock:
            known = set(self._jobs)
        for entry in self.root.iterdir():
            if entry.is_dir() and JOB_ID_RE.match(entry.name) and entry.name not in known:
                _remove_job_dir(self.root, entry)

    def _prune(self) -> None:
        """Zadrzi samo `max_jobs` najnovijih zavrsenih poslova."""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            stale = [job for job in jobs[self.max_jobs :] if job.finished]
            for job in stale:
                self._jobs.pop(job.id, None)
        for job in stale:
            _remove_job_dir(self.root, job.directory)


def _remove_job_dir(root: Path, directory: Path) -> None:
    """Obrisi folder posla, ali samo ako je zaista unutar `root` (mera opreza)."""
    try:
        resolved_root = root.resolve()
        resolved = directory.resolve()
    except OSError:  # pragma: no cover - retko (nestali folder na Windows-u)
        return
    if resolved.parent != resolved_root or not JOB_ID_RE.match(resolved.name):
        return
    shutil.rmtree(resolved, ignore_errors=True)


# --- Nazivi fajlova ------------------------------------------------------------------


def safe_stem(filename: str) -> str:
    """Naziv koji je korisnik poslao -> bezbedan naziv fajla bez ekstenzije.

    Stiti od putanja u `filename` (npr. `../../.bashrc`) i od znakova koje neki od
    podrzanih OS-eva ne dozvoljava.
    """
    name = Path(filename or "").name
    stem = Path(name).stem if name else ""
    cleaned = _UNSAFE_NAME_CHARS.sub("_", stem).strip(" .")
    return cleaned[:MAX_STEM_LENGTH] or "snimak"


def safe_suffix(filename: str) -> str:
    """Ekstenzija ulaznog snimka (mala slova), ili `.mp3` ako je nema/nije podrzana."""
    suffix = Path(Path(filename or "").name).suffix.lower()
    return suffix if suffix in ALLOWED_SUFFIXES else ".mp3"


# --- Pipeline ------------------------------------------------------------------------


def build_params(
    grid: int = DEFAULT_GRID,
    split_pitch: int = DEFAULT_SPLIT_PITCH,
    monophonic: bool = False,
    snap_to_scale: bool = False,
    quantize: bool = True,
) -> TranscriptionParams:
    """Napravi `TranscriptionParams` iz vrednosti sa forme; validira opsege.

    Raises:
        ValueError: vrednost van dozvoljenog opsega (poruka ide korisniku kao 400).
    """
    if grid not in GRID_CHOICES:
        raise ValueError(f"grid mora biti jedno od {GRID_CHOICES} (4=cetvrtina, 16=sesnaestina)")
    if not MIN_SPLIT_PITCH <= split_pitch <= MAX_SPLIT_PITCH:
        raise ValueError(
            f"split_pitch mora biti izmedju {MIN_SPLIT_PITCH} i {MAX_SPLIT_PITCH} (60 = C4)"
        )

    return TranscriptionParams(
        grid=grid,
        quantize=quantize,
        snap_to_scale=snap_to_scale,
        hands=HandSplitParams(split_pitch=split_pitch, monophonic_melody=monophonic),
    )


def run_job(store: JobStore, job: Job) -> Job:
    """Pusti ceo pipeline (Taskovi 2-5) za jedan posao i upisi ishod u `job`.

    Pipeline se uvozi ovde (a ne na vrhu modula) da uvoz servera ostane lagan i da
    testovi mogu da podmene `transcribe_file` / `export_all`.
    """
    from .export import export_all
    from .transcribe import transcribe_file

    store.update(job, status="running", stage="prepoznavanje nota", progress=0.1)
    try:
        result = transcribe_file(job.input_path, job.params)
        if result.get("status") != "ok":
            reason = "; ".join(result.get("warnings") or []) or "transkripcija nije uspela"
            return store.update(
                job, status="error", stage="greska", progress=1.0, error=reason, result=result
            )

        store.update(job, stage="izvoz nota", progress=0.75, result=result)
        files = export_all(
            result,
            out_dir=job.directory,
            basename=job.stem,
            with_pdf=job.with_pdf,
        )
    except Exception as exc:  # pipeline nikada ne sme da obori server
        return store.update(job, status="error", stage="greska", progress=1.0, error=str(exc))

    return store.update(job, status="done", stage="gotovo", progress=1.0, files=files)


# --- JSON odgovori -------------------------------------------------------------------


def job_payload(job: Job, with_musicxml: bool = True) -> dict[str, Any]:
    """Stanje posla kao JSON-serializabilna mapa (isti oblik za sve rute).

    Kada je posao gotov, mapa nosi i analizu (tempo, tonalitet), note po rukama,
    linkove za preuzimanje i — ako je trazeno — ceo MusicXML za prikaz u browseru.
    """
    payload: dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress": round(float(job.progress), 3),
        "filename": job.filename,
        "created_at": job.created_at,
        "error": job.error,
        "warnings": list((job.result or {}).get("warnings") or []),
        "files": _file_links(job),
        "musicxml": None,
    }

    result = job.result or {}
    if job.status == "done":
        payload.update(
            {
                "duration_sec": result.get("duration_sec"),
                "tempo_bpm": result.get("tempo_bpm"),
                "key": result.get("key"),
                "time_signature": result.get("time_signature"),
                "right_hand": result.get("right_hand") or [],
                "left_hand": result.get("left_hand") or [],
                "note_counts": {
                    "right_hand": len(result.get("right_hand") or []),
                    "left_hand": len(result.get("left_hand") or []),
                },
            }
        )
        if with_musicxml:
            payload["musicxml"] = _read_musicxml(job)

    return payload


def _file_links(job: Job) -> dict[str, str | None]:
    """Linkovi za preuzimanje; `None` za ono sto nije napravljeno (npr. PDF)."""
    links: dict[str, str | None] = {}
    for kind, (key, _suffix, _mime) in DOWNLOAD_KINDS.items():
        path = job.files.get(key)
        links[kind] = f"/download/{job.id}/{kind}" if path and Path(path).is_file() else None
    return links


def _read_musicxml(job: Job) -> str | None:
    """Sadrzaj MusicXML fajla (za prikaz u browseru), ako postoji."""
    path = job.files.get("musicxml")
    if not path or not Path(path).is_file():
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return None


# --- FastAPI aplikacija --------------------------------------------------------------


def create_app(
    jobs_dir: str | Path | None = None,
    max_upload_mb: float | None = None,
    max_jobs: int | None = None,
):
    """Napravi i vrati FastAPI aplikaciju.

    Args:
        jobs_dir: Folder za rezultate; podrazumevano `NOTEMKR_JOBS_DIR` ili `jobs/`.
        max_upload_mb: Najveci dozvoljeni upload; podrazumevano `NOTEMKR_MAX_UPLOAD_MB`.
        max_jobs: Koliko poslova se cuva na disku; podrazumevano `NOTEMKR_MAX_JOBS`.

    Uvoz FastAPI je lenj tako da `import notemkr` ne zahteva instaliran web stack.
    """
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.concurrency import run_in_threadpool

    root = Path(jobs_dir or os.environ.get("NOTEMKR_JOBS_DIR") or DEFAULT_JOBS_DIR)
    upload_limit = int(
        float(max_upload_mb or os.environ.get("NOTEMKR_MAX_UPLOAD_MB") or DEFAULT_MAX_UPLOAD_MB)
        * 1024
        * 1024
    )
    store = JobStore(root, int(max_jobs or os.environ.get("NOTEMKR_MAX_JOBS") or DEFAULT_MAX_JOBS))

    @asynccontextmanager
    async def lifespan(app: Any):
        store.root.mkdir(parents=True, exist_ok=True)
        store.cleanup_orphans()  # ostaci od ranijeg pokretanja vise nisu dohvatljivi
        yield
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="notemkr",
        version="0.1.0",
        description="Lokalni server: MP3 -> note za harmoniku (leva + desna ruka).",
        lifespan=lifespan,
    )
    app.state.store = store
    # Jedan radnik: transkripcija je CPU-intenzivna, pa paralelni poslovi ne bi bili
    # brzi — samo bi se otimali o iste jezgre.
    app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notemkr-job")

    @app.get("/health")
    def health() -> dict[str, Any]:
        from .audio import ffmpeg_available
        from .export import find_musescore

        return {
            "status": "ok",
            "app": "notemkr",
            "version": "0.1.0",
            "ffmpeg": ffmpeg_available(),
            "musescore": find_musescore() is not None,  # bez njega nema PDF-a
        }

    @app.post("/transcribe")
    async def transcribe(
        file: Annotated[UploadFile, File(description="snimak: MP3, WAV, M4A, FLAC...")],
        grid: Annotated[int, Form(description="4=cetvrtina, 8=osmina, 16=sesnaestina")] = (
            DEFAULT_GRID
        ),
        split_pitch: Annotated[int, Form(description="granica ruku, MIDI visina")] = (
            DEFAULT_SPLIT_PITCH
        ),
        monophonic: Annotated[bool, Form(description="desna ruka kao jedna linija")] = False,
        snap_to_scale: Annotated[bool, Form(description="izbaci vanlestvicne note")] = False,
        quantize: Annotated[bool, Form(description="kvantizuj ritam")] = True,
        pdf: Annotated[bool, Form(description="probaj i PDF (treba MuseScore)")] = True,
        background: Annotated[bool, Form(description="ne cekaj rezultat, prati /status")] = False,
    ):
        """Primi snimak, pokreni pipeline i vrati note + linkove za preuzimanje."""
        suffix = Path(Path(file.filename or "").name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"Nepodrzan format '{suffix or file.filename}'. "
                f"Podrzano: {', '.join(ALLOWED_SUFFIXES)}.",
            )

        try:
            params = build_params(grid, split_pitch, monophonic, snap_to_scale, quantize)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job = store.create(file.filename or "snimak.mp3", params, with_pdf=pdf)
        try:
            await _save_upload(file, job.input_path, upload_limit)
        except UploadError as exc:
            store.remove(job)
            status_code = 413 if "velik" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - I/O greska pri upisu
            store.remove(job)
            raise HTTPException(status_code=500, detail=f"Upload nije sacuvan: {exc}") from exc

        if background:
            store.update(job, stage="u redu za obradu")
            app.state.executor.submit(run_job, store, job)
            return JSONResponse(status_code=202, content=job_payload(job))

        await run_in_threadpool(run_job, store, job)
        payload = job_payload(job)
        if job.status == "error":
            return JSONResponse(status_code=500, content=payload)
        return payload

    @app.get("/status/{job_id}")
    def status(job_id: str, musicxml: bool = False) -> dict[str, Any]:
        """Stanje posla; `?musicxml=true` vraca i partituru kada je gotova."""
        job = _require_job(job_id)
        return job_payload(job, with_musicxml=musicxml)

    @app.get("/download/{job_id}/{kind}")
    def download(job_id: str, kind: str):
        """Preuzmi rezultat posla: `midi`, `musicxml` ili `pdf`."""
        job = _require_job(job_id)
        if kind not in DOWNLOAD_KINDS:
            raise HTTPException(
                status_code=404,
                detail=f"Nepoznat tip '{kind}'. Podrzano: {', '.join(DOWNLOAD_KINDS)}.",
            )

        key, suffix, media_type = DOWNLOAD_KINDS[kind]
        path = job.files.get(key)
        if path is None or not Path(path).is_file():
            if job.status != "done":
                raise HTTPException(status_code=409, detail=f"Posao jos nije gotov ({job.status}).")
            detail = f"Fajl '{kind}' ne postoji za ovaj posao."
            if kind == "pdf":
                detail += " PDF se pravi samo ako je MuseScore instaliran."
            raise HTTPException(status_code=404, detail=detail)

        return FileResponse(
            path=Path(path),
            media_type=media_type,
            filename=f"{job.stem}{suffix}",
        )

    def _require_job(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Nepoznat job_id: {job_id}")
        return job

    # Frontend se montira poslednji, da API rute imaju prednost nad statickim fajlovima.
    if (WEB_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    else:  # pragma: no cover - samo dok frontend ne postoji

        @app.get("/")
        def index() -> dict[str, str]:
            return {"status": "ok", "info": "Frontend nije nadjen; API je na /transcribe."}

    return app


async def _save_upload(upload: Any, target: Path, limit_bytes: int) -> int:
    """Upisi upload na disk u komadima, uz tvrdo ogranicenje velicine.

    Citanje u komadima znaci da ni ogroman fajl ne ulazi ceo u memoriju, a limit
    se proverava u hodu (a ne posle upisa).

    Returns:
        Broj upisanih bajtova.

    Raises:
        UploadError: fajl je prazan ili prelazi dozvoljenu velicinu.
    """
    total = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit_bytes:
                    raise UploadError(
                        f"Snimak je prevelik (limit je {limit_bytes // (1024 * 1024)} MB)."
                    )
                out.write(chunk)
    except UploadError:
        target.unlink(missing_ok=True)
        raise

    if total == 0:
        target.unlink(missing_ok=True)
        raise UploadError("Poslati fajl je prazan.")
    return total


# --- Pokretanje ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notemkr",
        description="Pokreni lokalni notemkr server (drag-drop MP3 -> note u browseru).",
    )
    parser.add_argument("--host", default=os.environ.get("NOTEMKR_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("NOTEMKR_PORT", DEFAULT_PORT))
    )
    parser.add_argument(
        "--jobs-dir", type=Path, default=None, help="folder za rezultate (podrazumevano jobs/)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="ne otvaraj browser pri pokretanju"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Pokreni lokalni server (konzolna skripta `notemkr`).

    Za spakovanu (.exe) verziju ulazna tacka je `notemkr.launcher` — ista aplikacija,
    ali sa trazenjem slobodnog porta i porukama za netehnickog korisnika.
    """
    import uvicorn

    from .runtime import prepare_runtime

    prepare_runtime()
    args = build_parser().parse_args(argv)
    app = create_app(jobs_dir=args.jobs_dir)
    url = f"http://{args.host}:{args.port}/"

    print(f"notemkr radi na {url}  (Ctrl+C za prekid)")
    if not args.no_browser and (WEB_DIR / "index.html").is_file():
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except OSError as exc:
        print(f"Ne mogu da zauzmem {args.host}:{args.port} ({exc}). Probaj --port 8001.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
