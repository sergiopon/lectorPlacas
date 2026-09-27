from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.errors import ProcessingCancelledError
from lector_placas.gui import processing as processing_module
from lector_placas.gui.main_window import TAB_TITLES, WINDOW_TITLE, MainWindow
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


def test_window_title_and_tabs(config: AppConfig, qapp) -> None:
    window = MainWindow(_session(config), PurgeResult(1, 2, 3, 4, 5))
    assert window.windowTitle() == WINDOW_TITLE
    assert window.windowTitle() == "lectorPlacas"
    tabs = window.tabs()
    assert tabs.count() == len(TAB_TITLES)
    assert [tabs.tabText(index) for index in range(tabs.count())] == list(TAB_TITLES)


def test_status_bar_shows_purge_counts(config: AppConfig, qapp) -> None:
    window = MainWindow(_session(config), PurgeResult(1, 2, 3, 4, 5))
    message = window.statusBar().currentMessage()
    assert "recortes=1" in message
    assert "avistamientos=2" in message
    assert "corridas=3" in message
    assert "placas=4" in message
    assert "exportaciones=5" in message


def test_close_event_closes_session(config: AppConfig, qapp) -> None:
    session = _session(config)
    window = MainWindow(session, PurgeResult(0, 0, 0, 0, 0))
    event = QCloseEvent()
    window.closeEvent(event)
    assert session.repository.closed is True
    assert event.isAccepted() is True


class _FakeRepository:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _BlockingUseCase:
    def execute(self, video: Path, sha: str, progress) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if progress.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
            time.sleep(0.005)
        raise ProcessingCancelledError("procesamiento cancelado por el operador")


def _patch_processing(monkeypatch) -> None:
    monkeypatch.setattr(composition, "build_repository", lambda config, keys: _FakeRepository())
    monkeypatch.setattr(composition, "build_crop_store", lambda config, keys: object())
    monkeypatch.setattr(
        composition,
        "build_process_video",
        lambda config, profile, repo, crop_store, clock: _BlockingUseCase(),
    )
    monkeypatch.setattr(processing_module, "sha256_file", lambda path: "a" * 64)


def test_close_while_busy_asks_and_can_abort(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch)
    window = MainWindow(session, PurgeResult(0, 0, 0, 0, 0))
    tab = window.tabs().widget(0)
    tab.start(Path("/videos/x.mp4"), "calle_lenta")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is False
    assert session.repository.closed is False
    tab.cancel()
    tab.wait_for_worker()


def test_close_while_busy_cancels_and_waits(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch)
    window = MainWindow(session, PurgeResult(0, 0, 0, 0, 0))
    tab = window.tabs().widget(0)
    tab.start(Path("/videos/x.mp4"), "calle_lenta")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is True
    assert session.repository.closed is True
