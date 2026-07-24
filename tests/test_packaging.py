"""Testovi sloja za pakovanje: putanje u paketu, PATH sa ffmpeg-om i launcher.

Sam .exe se ovde ne pravi (za to sluzi `packaging/smoke_test.py` nad `dist/`), ali
se proverava sve sto odlucuje da li ce spakovana verzija raditi: da li se resursi
traze na pravom mestu kada je `sys.frozen` postavljen, da li prilozeni `ffmpeg`
zavrsi u PATH-u i da li launcher ume da nadje slobodan port.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

from notemkr import runtime


@pytest.fixture
def frozen(monkeypatch, tmp_path: Path) -> Path:
    """Pretvaraj se da kod radi iz PyInstaller paketa raspakovanog u `tmp_path`."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    return tmp_path


# --- Putanje -------------------------------------------------------------------------


def test_iz_izvornog_koda_putanje_pokazuju_na_repo():
    """Bez pakovanja se nista ne menja: resursi i `jobs/` su u korenu repoa."""
    root = runtime.bundle_dir()
    assert (root / "notemkr" / "runtime.py").is_file()
    assert runtime.web_dir() == root / "web"
    assert runtime.default_jobs_dir() == root / "jobs"
    assert not runtime.is_frozen()


def test_u_paketu_resursi_idu_iz_meipass_a(frozen: Path):
    assert runtime.is_frozen()
    assert runtime.bundle_dir() == frozen
    assert runtime.web_dir() == frozen / "web"
    assert runtime.bin_dir() == frozen / "bin"


def test_u_paketu_jobs_folder_nije_pored_exe_a(frozen: Path):
    """Rezultati moraju u korisnicki folder — pored .exe-a se cesto ne sme pisati."""
    jobs = runtime.default_jobs_dir()
    assert jobs == runtime.user_data_dir() / "jobs"
    assert frozen not in jobs.parents
    assert jobs.parent.name == runtime.APP_NAME


def test_user_data_dir_postuje_windows_promenljive(monkeypatch, tmp_path: Path):
    if sys.platform != "win32":
        pytest.skip("provera vazi za Windows granu")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runtime.user_data_dir() == tmp_path / runtime.APP_NAME


def test_server_koristi_runtime_putanje():
    """Server ne sme da racuna putanje preko `__file__` (u paketu ih nema)."""
    from notemkr import server

    assert server.WEB_DIR == runtime.web_dir()
    assert server.DEFAULT_JOBS_DIR == runtime.default_jobs_dir()


# --- Prilozeni ffmpeg ----------------------------------------------------------------


def test_prilozeni_ffmpeg_ide_na_pocetak_path_a(frozen: Path, monkeypatch):
    tools = frozen / "bin"
    tools.mkdir()
    (tools / "ffmpeg").write_text("#!/bin/sh\n")
    monkeypatch.setenv("PATH", "/usr/bin")

    runtime.prepare_runtime()

    import os

    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools)
    assert runtime.bundled_ffmpeg() == tools / "ffmpeg"


def test_prepare_runtime_je_idempotentan(frozen: Path, monkeypatch):
    """Visestruki poziv ne sme da nagomilava isti folder u PATH-u."""
    import os

    tools = frozen / "bin"
    tools.mkdir()
    monkeypatch.setenv("PATH", "/usr/bin")

    runtime.prepare_runtime()
    runtime.prepare_runtime()
    runtime.prepare_runtime()

    assert os.environ["PATH"].split(os.pathsep).count(str(tools)) == 1


def test_bez_prilozenog_ffmpeg_a_path_ostaje_isti(frozen: Path, monkeypatch):
    import os

    monkeypatch.setenv("PATH", "/usr/bin")
    runtime.prepare_runtime()
    assert os.environ["PATH"] == "/usr/bin"
    assert runtime.bundled_ffmpeg() is None


# --- Launcher ------------------------------------------------------------------------


def test_launcher_preskace_zauzet_port():
    """Druga pokrenuta kopija ne sme da pukne, nego da uzme sledeci slobodan port."""
    from notemkr import launcher

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy = taken.getsockname()[1]

        chosen = launcher.find_free_port("127.0.0.1", busy)

    assert chosen > busy


def test_launcher_vraca_trazeni_port_kada_je_slobodan():
    from notemkr import launcher

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]

    assert launcher.find_free_port("127.0.0.1", free) == free


def test_wait_until_serving_odustane_kada_niko_ne_slusa():
    from notemkr import launcher

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    assert launcher.wait_until_serving("127.0.0.1", port, timeout=0.4, poll=0.1) is False


def test_banner_pominje_adresu_i_da_prozor_ostane_otvoren(capsys):
    """Uputstvo je jedino sto netehnicki korisnik dobije — mora da sadrzi adresu."""
    from notemkr import launcher

    launcher.print_banner("http://127.0.0.1:8000/")
    printed = capsys.readouterr().out

    assert "http://127.0.0.1:8000/" in printed
    assert "OSTANE OTVOREN" in printed


# --- Spec fajl -----------------------------------------------------------------------


def test_spec_pakuje_web_model_i_iskljucuje_tensorflow():
    """Cuva dogovor izmedju `notemkr.spec` i onoga sto runtime ocekuje u paketu."""
    spec = (runtime.bundle_dir() / "packaging" / "notemkr.spec").read_text(encoding="utf-8")

    assert f'"{runtime.WEB_SUBDIR}"' in spec  # frontend ide u paket pod istim imenom
    assert f'(str(entry), "{runtime.BIN_SUBDIR}")' in spec  # ffmpeg u bin/
    assert "basic_pitch" in spec  # ONNX model
    assert '"tensorflow",' in spec  # i to iskljucen
