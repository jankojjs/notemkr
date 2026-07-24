"""Testovi web sloja: /transcribe, /status, /download i serviranje frontend-a.

Pipeline je spor (model + inferencija), pa ga vecina testova podmenjuje lazniakom:
`run_job` uvozi `transcribe_file` i `export_all` tek u trenutku poziva, pa je dovoljno
zameniti ih na njihovim modulima. Jedan integracioni test (na pravom snimku) proverava
da ceo lanac zaista radi — on se preskace bez basic-pitch-a.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import requires_basic_pitch, requires_sample, requires_web_stack

pytestmark = requires_web_stack


@pytest.fixture
def client(tmp_path: Path):
    """TestClient nad sveze napravljenom aplikacijom, sa jobs folderom u tmp_path."""
    from fastapi.testclient import TestClient

    from notemkr.server import create_app

    app = create_app(jobs_dir=tmp_path / "jobs", max_upload_mb=1)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Podmeni transkripciju i izvoz brzim lazniakom koji pise prave fajlove."""
    from notemkr import export, transcribe

    calls: dict[str, object] = {}

    def fake_transcribe_file(path, params=None):
        calls["path"] = Path(path)
        calls["params"] = params
        return {
            "source": str(path),
            "status": "ok",
            "duration_sec": 9.0,
            "tempo_bpm": 120.0,
            "key": "G major",
            "time_signature": "4/4",
            "right_hand": [{"pitch": 67, "start": 0.0, "end": 0.5, "velocity": 80}],
            "left_hand": [{"pitch": 43, "start": 0.0, "end": 1.0, "velocity": 70}],
            "warnings": ["test upozorenje"],
        }

    def fake_export_all(result, out_dir=None, basename=None, with_pdf=True):
        directory = Path(out_dir)
        midi = directory / f"{basename}.mid"
        musicxml = directory / f"{basename}.musicxml"
        midi.write_bytes(b"MThd-fake")
        musicxml.write_text("<score-partwise/>", encoding="utf-8")
        calls["with_pdf"] = with_pdf
        return {"midi": midi, "musicxml": musicxml, "pdf": None}

    monkeypatch.setattr(transcribe, "transcribe_file", fake_transcribe_file)
    monkeypatch.setattr(export, "export_all", fake_export_all)
    return calls


def upload(client, name: str = "pesma.mp3", data: bytes = b"fake-mp3-bytes", **form):
    files = {"file": (name, data, "audio/mpeg")}
    return client.post("/transcribe", files=files, data=form)


# --- health i frontend ---------------------------------------------------------------


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["ffmpeg"], bool)


def test_frontend_se_posluzuje(client):
    """Na `/` stoji drag-drop stranica iz `web/` (a ne API odgovor)."""
    response = client.get("/")

    assert response.status_code == 200
    assert "Prevuci" in response.text


def test_osmd_je_lokalni_asset(client):
    """OpenSheetMusicDisplay se sluzi lokalno — bez CDN-a, pa radi i offline."""
    response = client.get("/vendor/opensheetmusicdisplay.min.js")

    assert response.status_code == 200
    assert len(response.content) > 100_000


# --- /transcribe ---------------------------------------------------------------------


def test_transcribe_vraca_note_linkove_i_musicxml(client, fake_pipeline):
    response = upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["filename"] == "pesma.mp3"
    assert body["tempo_bpm"] == 120.0
    assert body["key"] == "G major"
    assert body["note_counts"] == {"right_hand": 1, "left_hand": 1}
    assert body["warnings"] == ["test upozorenje"]
    assert body["musicxml"] == "<score-partwise/>"
    assert body["files"]["midi"] == f"/download/{body['job_id']}/midi"
    assert body["files"]["musicxml"] == f"/download/{body['job_id']}/musicxml"
    assert body["files"]["pdf"] is None  # MuseScore nije garantovan
    assert json.dumps(body)  # ceo odgovor mora biti JSON-serializabilan


def test_transcribe_prosledjuje_podesavanja_pipeline_u(client, fake_pipeline):
    response = upload(client, grid=16, split_pitch=62, monophonic="true", pdf="false")

    assert response.status_code == 200
    params = fake_pipeline["params"]
    assert params.grid == 16
    assert params.hands.split_pitch == 62
    assert params.hands.monophonic_melody is True
    assert fake_pipeline["with_pdf"] is False


def test_transcribe_odbija_nepodrzan_format(client, fake_pipeline):
    response = upload(client, name="dokument.pdf")

    assert response.status_code == 400
    assert "Nepodrzan format" in response.json()["detail"]


def test_transcribe_odbija_los_grid(client, fake_pipeline):
    response = upload(client, grid=7)

    assert response.status_code == 400
    assert "grid" in response.json()["detail"]


def test_transcribe_odbija_prevelik_fajl(client, fake_pipeline, tmp_path):
    response = upload(client, data=b"x" * (2 * 1024 * 1024))  # limit je 1 MB

    assert response.status_code == 413
    assert not list((tmp_path / "jobs").glob("*/*"))  # nedovrsen upload se brise


def test_transcribe_odbija_prazan_fajl(client, fake_pipeline):
    response = upload(client, data=b"")

    assert response.status_code == 400
    assert "prazan" in response.json()["detail"]


def test_transcribe_vraca_gresku_pipeline_a_bez_pada_servera(client, monkeypatch):
    from notemkr import transcribe

    def boom(path, params=None):
        raise RuntimeError("model nije dostupan")

    monkeypatch.setattr(transcribe, "transcribe_file", boom)

    response = upload(client)

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert "model nije dostupan" in body["error"]


def test_transcribe_cuva_snimak_pod_bezbednim_imenom(client, fake_pipeline):
    """Naziv iz upload-a ne sme da izadje iz foldera posla."""
    response = upload(client, name="../../zlocesto ime!.mp3")

    assert response.status_code == 200
    saved = fake_pipeline["path"]
    assert saved.name == "zlocesto ime_.mp3"
    assert saved.parent.name == response.json()["job_id"]


# --- /status i pozadinska obrada -----------------------------------------------------


def test_background_obrada_i_status(client, fake_pipeline):
    response = upload(client, background="true")

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    for _ in range(100):  # posao se vrti u thread pool-u
        body = client.get(f"/status/{job_id}").json()
        if body["status"] in ("done", "error"):
            break
        import time

        time.sleep(0.05)

    assert body["status"] == "done"
    assert body["progress"] == 1.0
    assert body["musicxml"] is None  # podrazumevano bez partiture
    assert client.get(f"/status/{job_id}?musicxml=true").json()["musicxml"] == "<score-partwise/>"


def test_status_nepoznatog_posla(client):
    assert client.get("/status/" + "0" * 32).status_code == 404


def test_status_odbija_putanju_umesto_id_a(client):
    assert client.get("/status/..%2F..%2Fetc").status_code == 404


# --- /download -----------------------------------------------------------------------


def test_download_midi_i_musicxml(client, fake_pipeline):
    job_id = upload(client).json()["job_id"]

    midi = client.get(f"/download/{job_id}/midi")
    musicxml = client.get(f"/download/{job_id}/musicxml")

    assert midi.status_code == 200
    assert midi.content == b"MThd-fake"
    assert "pesma.mid" in midi.headers["content-disposition"]
    assert musicxml.status_code == 200
    assert musicxml.text == "<score-partwise/>"


def test_download_pdf_kad_ga_nema(client, fake_pipeline):
    job_id = upload(client).json()["job_id"]

    response = client.get(f"/download/{job_id}/pdf")

    assert response.status_code == 404
    assert "MuseScore" in response.json()["detail"]


def test_download_nepoznat_tip(client, fake_pipeline):
    job_id = upload(client).json()["job_id"]

    assert client.get(f"/download/{job_id}/exe").status_code == 404


def test_download_nepoznat_posao(client):
    assert client.get(f"/download/{'a' * 32}/midi").status_code == 404


# --- integracija (pravi pipeline) ----------------------------------------------------


@requires_basic_pitch
@requires_sample
def test_transcribe_na_pravom_snimku(client, sample_mp3):
    """Acceptance: upload MP3 -> JSON sa linkovima i MusicXML-om koji se preuzima."""
    with sample_mp3.open("rb") as handle:
        response = client.post(
            "/transcribe",
            files={"file": (sample_mp3.name, handle, "audio/mpeg")},
            data={"pdf": "false"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done"
    assert body["tempo_bpm"] > 0
    assert body["note_counts"]["right_hand"] > 0
    assert body["musicxml"].lstrip().startswith("<?xml")
    assert "score-partwise" in body["musicxml"]

    for kind in ("midi", "musicxml"):
        download = client.get(body["files"][kind])
        assert download.status_code == 200
        assert download.content
