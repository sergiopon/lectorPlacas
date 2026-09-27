from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.ports import ProgressUpdate, RunRecord, RunStats, RunStatus
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.errors import InputValidationError
from lector_placas.gui import processing as processing_module
from lector_placas.gui.process_tab import RUN_COLUMNS, ProcessTab, RunsTableModel
from lector_placas.gui.session import GuiSession
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)


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


class _FakeRepository:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _ImmediateUseCase:
    def execute(self, video: Path, sha: str, progress) -> RunResult:
        return RunResult(1, RunStats(10, 8, 3, 2, 1, 0, 500, 1000))


def _patch_processing(monkeypatch, use_case: _ImmediateUseCase) -> None:
    monkeypatch.setattr(composition, "build_repository", lambda config, keys: _FakeRepository())
    monkeypatch.setattr(composition, "build_crop_store", lambda config, keys: object())
    monkeypatch.setattr(
        composition,
        "build_process_video",
        lambda config, profile, repo, crop_store, clock: use_case,
    )
    monkeypatch.setattr(processing_module, "sha256_file", lambda path: "a" * 64)


def test_profiles_combo_uses_config_and_default(config: AppConfig, qapp) -> None:
    tab = ProcessTab(_session(config))
    combo = tab._profile_combo
    assert [combo.itemText(i) for i in range(combo.count())] == list(config.profiles)
    assert combo.currentText() == config.default_profile


def test_invalid_video_shows_warning_and_does_not_start(
    config: AppConfig, monkeypatch, qapp
) -> None:
    tab = ProcessTab(_session(config))
    tab._video = Path("/videos/x.mp4")

    def boom(cfg: AppConfig, path: Path) -> Path:
        raise InputValidationError("video inválido")

    monkeypatch.setattr(composition, "validated_video", boom)
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    tab._process_button.click()
    assert len(warnings) == 1
    assert warnings[0][2] == "video inválido"
    assert tab.is_busy() is False


def test_start_disables_controls_and_emits_busy(config: AppConfig, monkeypatch, qapp) -> None:
    _patch_processing(monkeypatch, _ImmediateUseCase())
    tab = ProcessTab(_session(config))
    busy: list[bool] = []
    tab.busy_changed.connect(busy.append)
    tab.start(Path("/videos/x.mp4"), "calle_lenta")
    assert tab.is_busy() is True
    assert tab._choose_button.isEnabled() is False
    assert tab._profile_combo.isEnabled() is False
    assert tab._process_button.isEnabled() is False
    assert tab._cancel_button.isEnabled() is True
    assert busy == [True]
    tab.wait_for_worker()


def _assert_controls_restored(tab: ProcessTab) -> None:
    """Verifica que los controles estén habilitados tras el procesamiento."""
    assert tab.is_busy() is False
    assert tab._choose_button.isEnabled() is True
    assert tab._profile_combo.isEnabled() is True
    assert tab._process_button.isEnabled() is True
    assert tab._cancel_button.isEnabled() is False


def _create_session_with_tracked_list_runs(
    config: AppConfig, monkeypatch, calls: list[tuple[int, int]]
) -> GuiSession:
    """Crea una sesión con repositorio que registra llamadas a list_runs."""
    repository = InMemoryPlateRepository()
    original = repository.list_runs

    def list_runs(limit: int, offset: int) -> list[RunRecord]:
        calls.append((limit, offset))
        return original(limit, offset)

    monkeypatch.setattr(repository, "list_runs", list_runs)
    return GuiSession(
        config,
        FakeKeyProvider(),
        FakeClock(),
        repository,
        repository,
        InMemoryCropStore(),
        InMemoryExportStore(),
    )


def test_finish_restores_controls_and_refreshes_runs(config: AppConfig, monkeypatch, qapp) -> None:
    calls: list[tuple[int, int]] = []
    session = _create_session_with_tracked_list_runs(config, monkeypatch, calls)
    _patch_processing(monkeypatch, _ImmediateUseCase())
    tab = ProcessTab(session)
    initial = len(calls)
    finished: list[bool] = []
    tab.run_finished.connect(lambda: finished.append(True))
    loop = QEventLoop()
    tab.run_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    tab.start(Path("/videos/x.mp4"), "calle_lenta")
    loop.exec()
    assert finished == [True]
    _assert_controls_restored(tab)
    assert len(calls) > initial
    tab.wait_for_worker()


def test_progress_updates_bar(config: AppConfig, qapp) -> None:
    tab = ProcessTab(_session(config))
    tab._on_progress(ProgressUpdate(10, 5, 250, 1000, 3))
    assert tab._progress_bar.maximum() == 1000
    assert tab._progress_bar.value() == 250
    tab._on_progress(ProgressUpdate(10, 5, 100, None, 3))
    assert tab._progress_bar.maximum() == 0
    assert tab._progress_bar.minimum() == 0


def _assert_headers(model: RunsTableModel) -> None:
    """Verifica que los encabezados de columna sean correctos."""
    for column, title in enumerate(RUN_COLUMNS):
        assert model.headerData(column, Qt.Orientation.Horizontal) == title


def _assert_completed_row(model: RunsTableModel) -> None:
    """Verifica los datos de una fila de corrida completada."""
    assert model.data(model.index(0, 0)) == "1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", model.data(model.index(0, 1)) or "")
    assert model.data(model.index(0, 2)) == "calle_lenta"
    assert model.data(model.index(0, 3)) == "completada"
    assert model.data(model.index(0, 4)) == "01:01"
    assert model.data(model.index(0, 5)) == "5"
    assert model.data(model.index(0, 6)) == "2"
    assert model.data(model.index(0, 7)) == "1"
    assert model.data(model.index(0, 8)) == "6.10x"


def _assert_running_row(model: RunsTableModel) -> None:
    """Verifica los datos de una fila de corrida en curso con valores desconocidos."""
    assert model.data(model.index(1, 2)) == "calle_rapida"
    assert model.data(model.index(1, 3)) == "en curso"
    assert model.data(model.index(1, 4)) == "n/d"
    assert model.data(model.index(1, 5)) == "n/d"
    assert model.data(model.index(1, 6)) == "n/d"
    assert model.data(model.index(1, 7)) == "n/d"
    assert model.data(model.index(1, 8)) == "n/d"


def test_runs_model_formats_rows(qapp) -> None:
    model = RunsTableModel()
    completed = RunRecord(
        run_id=1,
        profile="calle_lenta",
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 9, 24, 12, 1, tzinfo=UTC),
        duration_ms=61000,
        frames_processed=100,
        sightings_confirmed=5,
        sightings_unverified=2,
        tracks_without_reading=1,
        processing_ms=10000,
    )
    running = RunRecord(
        run_id=2,
        profile="calle_rapida",
        status=RunStatus.RUNNING,
        started_at=datetime(2026, 9, 24, 13, 0, tzinfo=UTC),
        finished_at=None,
        duration_ms=None,
        frames_processed=None,
        sightings_confirmed=None,
        sightings_unverified=None,
        tracks_without_reading=None,
        processing_ms=None,
    )
    model.set_runs([completed, running])
    assert model.rowCount() == 2
    assert model.columnCount() == len(RUN_COLUMNS)
    _assert_headers(model)
    _assert_completed_row(model)
    _assert_running_row(model)
