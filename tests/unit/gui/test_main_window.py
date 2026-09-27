from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ProcessingCancelledError
from lector_placas.gui import processing as processing_module
from lector_placas.gui.main_window import PROCESS_PAGE, PURGE_MESSAGE, READINGS_PAGE, MainWindow
from lector_placas.gui.session import GuiSession
from lector_placas.gui.tools_dialogs import RUNS_TITLE, TOOLS_TITLE
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
VIDEO = Path("/videos/camion.mp4")
NO_PURGE = PurgeResult(0, 0, 0, 0, 0)


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


def _window(session: GuiSession, purge: PurgeResult = NO_PURGE) -> MainWindow:
    return MainWindow(session, purge)


def _start_run(session: GuiSession) -> int:
    return session.repository.start_run(RunStart("a" * 64, "calle_lenta", VIDEO_INFO, CREATED_AT))


def _add_sighting(
    session: GuiSession, run_id: int, status: ReviewStatus, text: str = "ABC123"
) -> int:
    reasons = () if status is ReviewStatus.CONFIRMED else (UnverifiedReason.LOW_CONFIDENCE,)
    plate = ConsolidatedPlate(text, 0.8, 0.9, 3, status, reasons, ())
    return session.repository.save_sighting(
        Sighting(run_id, 1, 0, 1000, VehicleType.CAR, plate, None, CREATED_AT)
    )


class _BlockingUseCase:
    """Caso de uso falso que espera la cancelación del operador."""

    def execute(self, video: Path, sha: str, progress) -> object:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if progress.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
            time.sleep(0.005)
        raise ProcessingCancelledError("procesamiento cancelado por el operador")


def _patch_processing(monkeypatch, session: GuiSession) -> None:
    monkeypatch.setattr(composition, "build_repository", lambda config, keys: session.repository)
    monkeypatch.setattr(composition, "build_crop_store", lambda config, keys: object())
    monkeypatch.setattr(
        composition, "build_process_video", lambda c, p, r, crop, clock: _BlockingUseCase()
    )
    monkeypatch.setattr(processing_module, "sha256_file", lambda path: "a" * 64)


def _start_busy(window: MainWindow) -> None:
    window._process_page._video = VIDEO
    window._process_page.start()


def test_initial_page_depends_on_data(config: AppConfig, qapp) -> None:
    empty = _window(_session(config))
    assert empty.current_page() == PROCESS_PAGE

    session = _session(config)
    _add_sighting(session, _start_run(session), ReviewStatus.UNVERIFIED)
    assert _window(session).current_page() == READINGS_PAGE


def test_nav_buttons_switch_pages(config: AppConfig, qapp) -> None:
    window = _window(_session(config))

    window._nav_buttons[READINGS_PAGE].click()
    assert window.current_page() == READINGS_PAGE
    assert window._nav_buttons[READINGS_PAGE].isChecked() is True

    window._nav_buttons[PROCESS_PAGE].click()
    assert window.current_page() == PROCESS_PAGE
    assert window._nav_buttons[PROCESS_PAGE].isChecked() is True
    assert window._nav_buttons[READINGS_PAGE].isChecked() is False


def test_pending_badge_updates(config: AppConfig, qapp) -> None:
    session = _session(config)
    _add_sighting(session, _start_run(session), ReviewStatus.UNVERIFIED)
    window = _window(session)
    readings = window._nav_buttons[READINGS_PAGE]

    assert readings.text() == "Lecturas (1 por revisar)"

    window._readings_page.pending_changed.emit(4)
    assert readings.text() == "Lecturas (4 por revisar)"

    window._readings_page.pending_changed.emit(0)
    assert readings.text() == "Lecturas"


def test_more_menu_has_tools_and_history(config: AppConfig, qapp) -> None:
    window = _window(_session(config))

    assert window._more_button.text() == "Más"
    assert [action.text() for action in window._more_button.menu().actions()] == [
        f"{TOOLS_TITLE}…",
        f"{RUNS_TITLE}…",
    ]


def test_review_requested_opens_readings_for_run(config: AppConfig, qapp) -> None:
    session = _session(config)
    run_id = _start_run(session)
    _add_sighting(session, run_id, ReviewStatus.UNVERIFIED)
    pending_free = _start_run(session)
    window = _window(session)

    window._process_page.review_requested.emit(run_id)

    assert window.current_page() == READINGS_PAGE
    assert window._readings_page._filters.run_id() == run_id
    assert window._readings_page._filters.status() is ReviewStatus.UNVERIFIED

    window._process_page.review_requested.emit(pending_free)
    assert window._readings_page._filters.run_id() == pending_free
    assert window._readings_page._filters.status() is None


def test_busy_propagates_to_readings(config: AppConfig, qapp) -> None:
    window = _window(_session(config))
    states: list[bool] = []
    window.busy_changed.connect(states.append)

    window._process_page.busy_changed.emit(True)

    assert states == [True]
    assert all(not button.isEnabled() for button in window._readings_page._panel._buttons)

    window._process_page.busy_changed.emit(False)
    assert states == [True, False]
    assert all(button.isEnabled() for button in window._readings_page._panel._buttons)


def test_status_bar_only_when_purge_deleted_something(config: AppConfig, qapp) -> None:
    empty = _window(_session(config), NO_PURGE)
    assert empty.statusBar().currentMessage() == ""

    window = _window(_session(config), PurgeResult(1, 2, 3, 4, 5, training_deleted=6))
    assert window.statusBar().currentMessage() == PURGE_MESSAGE.format(total=21)
    assert "21 datos vencidos" in window.statusBar().currentMessage()


def test_close_while_busy_asks_and_can_abort(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch, session)
    window = _window(session)
    _start_busy(window)

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is False
    assert session.repository.closed is False
    window._process_page.cancel()
    window._process_page.wait_for_worker()


def test_close_while_busy_cancels_and_waits(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch, session)
    window = _window(session)
    _start_busy(window)

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True
    assert session.repository.closed is True


def test_close_without_busy_closes_session(config: AppConfig, qapp) -> None:
    session = _session(config)
    window = _window(session)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is True
    assert session.repository.closed is True
