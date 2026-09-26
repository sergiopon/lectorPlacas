"""Tests de revisión de la spec 028 (ocultos al implementador).

Cubren un caso borde que la spec no enumera explícitamente: con la red realmente
bloqueada (`block_network()` sin sustituir), un intento de conexión en un adaptador
termina con el código de salida 7 (`NetworkAccessError`).
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.infrastructure import network_guard
from tests.fixtures.fakes import FakeKeyProvider
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def blocked_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    (tmp_path / "videos").mkdir()
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: FakeKeyProvider()
    )
    # Preservar las funciones originales de socket para restaurarlas al terminar,
    # y dejar que `main` aplique la guardia de red real (no sustituirla).
    monkeypatch.setattr(socket.socket, "connect", socket.socket.connect)
    monkeypatch.setattr(socket.socket, "connect_ex", socket.socket.connect_ex)
    monkeypatch.setattr(socket, "create_connection", socket.create_connection)
    monkeypatch.setattr(network_guard, "_BLOCKED", False, raising=False)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


def run(project: Path, *args: str) -> int:
    return cli_main.main(["--config", str(project / "config" / "lector.yaml"), *args])


def test_process_with_blocked_network_returns_code_7(
    blocked_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un intento de socket con la red bloqueada termina en código 7."""
    video = write_video(blocked_project / "videos" / "v.mp4", frames=2)

    def repository_with_socket_attempt(config, keys):  # type: ignore[no-untyped-def]
        socket.create_connection(("127.0.0.1", 9))
        raise AssertionError("no debería llegar aquí")

    monkeypatch.setattr(composition, "build_repository", repository_with_socket_attempt)
    assert run(blocked_project, "process", str(video)) == 7
