from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.infrastructure import network_guard
from tests.fixtures.fakes import FakeKeyProvider
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    (tmp_path / "videos").mkdir()
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: FakeKeyProvider()
    )
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


def run(project: Path, *args: str) -> int:
    return cli_main.main(["--config", str(project / "config" / "lector.yaml"), *args])


def test_purge_and_export_create_private_files(project: Path) -> None:
    assert run(project, "purge") == 0
    database = project / "data" / "lector.db"
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert run(project, "export") == 0
    exported = list((project / "data" / "exports").glob("sightings-*.csv"))
    assert len(exported) == 1
    assert (project / "logs" / "lector.log").exists()


def test_error_exit_codes(project: Path) -> None:
    assert run(project, "process", str(project / "videos" / "no-existe.mp4")) == 3
    outside = write_video(project / "fuera.mp4", frames=2)
    assert run(project, "process", str(outside)) == 3
    assert run(project, "models", "verify") == 4
    assert cli_main.main(["--config", str(project / "config" / "no.yaml"), "purge"]) == 2


@pytest.mark.gpu
@pytest.mark.skipif(not (MODELS / "yolo26n-coco").exists(), reason="modelos no disponibles")
def test_process_synthetic_video_end_to_end(project: Path) -> None:
    shutil.copytree(MODELS, project / "models")
    shutil.copy(ROOT / "config" / "models.yaml", project / "config" / "models.yaml")
    video = write_video(project / "videos" / "sintetico.mp4", frames=20, width=320, height=240)
    assert run(project, "process", str(video)) == 0
