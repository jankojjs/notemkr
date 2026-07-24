"""Lokalni web server (FastAPI) za drag-drop upload i prikaz nota.

U ovom scaffold-u server izlaze osnovni health endpoint i posluzuje `web/` frontend
kada bude postojao. Puna upload/transkripcija ruta dolazi u Tasku 7. Teske zavisnosti
(fastapi, uvicorn) se uvoze lenjivo unutar funkcija da uvoz paketa ostane lagan.
"""

from __future__ import annotations

from pathlib import Path

# Koren frontend foldera, relativno u odnosu na koren repozitorijuma (cross-platform).
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app():
    """Napravi i vrati FastAPI aplikaciju.

    Uvoz FastAPI je lenj tako da `import notemkr` ne zahteva instaliran web stack.
    """
    from fastapi import FastAPI

    app = FastAPI(title="notemkr", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": "notemkr"}

    return app


def main() -> None:
    """Pokreni lokalni server (konzolna skripta `notemkr`)."""
    import uvicorn

    uvicorn.run("notemkr.server:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
