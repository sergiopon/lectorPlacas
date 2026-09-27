from __future__ import annotations

from datetime import UTC, datetime

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.errors import RepositoryError
from lector_placas.gui.maintenance_tab import MaintenanceTab
from lector_placas.gui.session import GuiSession
from lector_placas.gui.tools_dialogs import RUNS_TITLE, TOOLS_TITLE, RunsDialog, ToolsDialog
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

CREATED_AT = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
VIDEO_INFO = VideoInfo(640, 480, 0, 60_000, 30.0, "h264")


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


def test_tools_dialog_wraps_maintenance_and_forwards_busy(config: AppConfig, qapp) -> None:
    dialog = ToolsDialog(_session(config), None)

    assert dialog.windowTitle() == TOOLS_TITLE
    assert isinstance(dialog._maintenance, MaintenanceTab)
    dialog.set_busy(True)
    assert dialog._maintenance._export_button.isEnabled() is False
    assert dialog._maintenance._purge_button.isEnabled() is False
    dialog.set_busy(False)
    assert dialog._maintenance._export_button.isEnabled() is True

    forwarded: list[bool] = []
    dialog.data_changed.connect(lambda: forwarded.append(True))
    dialog._maintenance.data_changed.emit()
    assert forwarded == [True]


def test_runs_dialog_lists_runs(config: AppConfig, qapp) -> None:
    session = _session(config)
    session.repository.start_run(RunStart("a" * 64, "calle_lenta", VIDEO_INFO, CREATED_AT))

    dialog = RunsDialog(session, None)

    assert dialog.windowTitle() == RUNS_TITLE
    assert dialog._model.rowCount() == 1
    assert dialog._message.text() == ""


def test_runs_dialog_shows_repository_error(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)

    def boom(limit: int, offset: int) -> list[object]:
        raise RepositoryError("base de datos bloqueada")

    monkeypatch.setattr(session.repository, "list_runs", boom)
    dialog = RunsDialog(session, None)

    assert dialog._model.rowCount() == 0
    assert dialog._message.text() == "base de datos bloqueada"


def test_titles_match_constants(qapp) -> None:
    assert TOOLS_TITLE == "Exportar, retención y métricas"
    assert RUNS_TITLE == "Historial de videos"
