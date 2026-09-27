from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.errors import KeyUnavailableError, RepositoryError
from lector_placas.gui import app
from lector_placas.gui.session import GuiSession
from lector_placas.infrastructure import network_guard
from lector_placas.infrastructure.config import AppConfig, load_config
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _restore_excepthook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    return tmp_path


@pytest.fixture
def config(project: Path) -> AppConfig:
    return load_config(project / "config" / "lector.yaml")


class _RecordingKeyProvider:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def master_key(self) -> bytes:
        self._log.append("master_key")
        return bytes(range(32))


class _FailingKeyProvider:
    def master_key(self) -> bytes:
        raise KeyUnavailableError("no hay clave maestra")


def _session(config: AppConfig) -> GuiSession:
    repository = InMemoryPlateRepository()
    return GuiSession(
        config,
        FakeKeyProvider(),
        FakeClock(),
        repository,
        repository,
        InMemoryCropStore(),
        InMemoryExportStore(),
    )


def _config_path(project: Path) -> str:
    return str(project / "config" / "lector.yaml")


def test_main_order_umask_key_guard_application(project: Path, monkeypatch, qapp) -> None:
    order: list[str] = []
    monkeypatch.setattr(app.os, "umask", lambda mask: order.append("umask") or 0o022)
    monkeypatch.setattr(network_guard, "block_network", lambda: order.append("guard"))
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: _RecordingKeyProvider(order)
    )
    monkeypatch.setattr(app, "_create_application", lambda: order.append("application") or qapp)
    monkeypatch.setattr(app, "_exec", lambda application: 0)
    monkeypatch.setattr(
        app, "open_session", lambda config, keys: (_session(config), PurgeResult(0, 0, 0, 0, 0))
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)

    code = app.main(["--config", _config_path(project)])

    assert code == 0
    assert order == ["umask", "master_key", "guard", "application"]


def test_main_blocks_network_even_if_prepare_fails(project: Path, monkeypatch, qapp) -> None:
    blocked: list[bool] = []
    dialogs: list[tuple] = []
    monkeypatch.setattr(app.os, "umask", lambda mask: 0o022)
    monkeypatch.setattr(network_guard, "block_network", lambda: blocked.append(True))
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: _FailingKeyProvider()
    )
    monkeypatch.setattr(app, "_create_application", lambda: qapp)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: dialogs.append(args))

    code = app.main(["--config", _config_path(project)])

    assert blocked == [True]
    assert code == 1
    assert len(dialogs) == 1
    assert app.KEY_HINT in dialogs[0][2]


def test_main_returns_exec_code_and_closes_session(
    project: Path, config: AppConfig, monkeypatch, qapp
) -> None:
    repository = InMemoryPlateRepository()
    session = GuiSession(
        config,
        FakeKeyProvider(),
        FakeClock(),
        repository,
        repository,
        InMemoryCropStore(),
        InMemoryExportStore(),
    )
    monkeypatch.setattr(app.os, "umask", lambda mask: 0o022)
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: FakeKeyProvider()
    )
    monkeypatch.setattr(app, "_create_application", lambda: qapp)
    monkeypatch.setattr(app, "_exec", lambda application: 0)
    monkeypatch.setattr(
        app, "open_session", lambda config, keys: (session, PurgeResult(0, 0, 0, 0, 0))
    )

    assert app.main(["--config", _config_path(project)]) == 0
    assert repository.closed is True


def test_main_session_error_shows_dialog(project: Path, monkeypatch, qapp) -> None:
    dialogs: list[tuple] = []

    def boom(config: AppConfig, keys) -> GuiSession:
        raise RepositoryError("x")

    monkeypatch.setattr(app.os, "umask", lambda mask: 0o022)
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(
        composition, "build_key_provider", lambda create_if_missing: FakeKeyProvider()
    )
    monkeypatch.setattr(app, "_create_application", lambda: qapp)
    monkeypatch.setattr(app, "open_session", boom)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: dialogs.append(args))

    assert app.main(["--config", _config_path(project)]) == 1
    assert len(dialogs) == 1
    assert dialogs[0][2] == "x"
