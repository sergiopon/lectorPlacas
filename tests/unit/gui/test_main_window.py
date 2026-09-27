from __future__ import annotations

from PySide6.QtGui import QCloseEvent

from lector_placas.application.purge_expired import PurgeResult
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
