from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.ports import ProgressUpdate, RunStart, RunStats, VideoInfo
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import (
    InputValidationError,
    ProcessingCancelledError,
    VideoSourceError,
)
from lector_placas.gui import process_page as page_module
from lector_placas.gui import processing as processing_module
from lector_placas.gui.labels import profile_label
from lector_placas.gui.process_page import ProcessPage
from lector_placas.gui.process_views import IdleView, eta_text
from lector_placas.gui.session import GuiSession
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
WAIT_MS = 5000


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


def _sighting(run_id: int, text: str, status: ReviewStatus) -> Sighting:
    reasons = () if status is ReviewStatus.CONFIRMED else (UnverifiedReason.LOW_CONFIDENCE,)
    plate = ConsolidatedPlate(text, 0.8, 0.9, 3, status, reasons, ())
    return Sighting(run_id, 1, 0, 1000, VehicleType.CAR, plate, None, CREATED_AT)


def _patch_processing(monkeypatch, session: GuiSession, use_case: object) -> None:
    """Sustituye la composición y el hash por fakes que ejecutan `use_case`."""
    monkeypatch.setattr(composition, "build_repository", lambda config, keys: session.repository)
    monkeypatch.setattr(composition, "build_crop_store", lambda config, keys: object())
    monkeypatch.setattr(composition, "build_process_video", lambda c, p, r, crop, clock: use_case)
    monkeypatch.setattr(processing_module, "sha256_file", lambda path: "a" * 64)


class _ImmediateUseCase:
    """Caso de uso falso que termina al instante con un resultado fijo."""

    def __init__(self, result: RunResult) -> None:
        self._result = result

    def execute(self, video: Path, sha: str, progress: object) -> RunResult:
        return self._result


class _BlockingUseCase:
    """Caso de uso falso que espera la cancelación del operador."""

    def execute(self, video: Path, sha: str, progress) -> RunResult:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if progress.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
            time.sleep(0.005)
        raise ProcessingCancelledError("procesamiento cancelado por el operador")


class _FailingUseCase:
    """Caso de uso falso que falla con un error del dominio."""

    def execute(self, video: Path, sha: str, progress: object) -> RunResult:
        raise VideoSourceError("video dañado")


class _Clock:
    """Reloj monótono falso que solo avanza cuando el test lo pide."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _start_and_wait(page: ProcessPage) -> None:
    """Arranca el procesamiento y espera a `run_finished` con un límite de 5 s."""
    loop = QEventLoop()
    page.run_finished.connect(loop.quit)
    QTimer.singleShot(WAIT_MS, loop.quit)
    page.start()
    loop.exec()
    page.wait_for_worker()


def _mime(*paths: Path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def _drag_event(mime: QMimeData) -> QDragEnterEvent:
    return QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drop_event(mime: QMimeData) -> QDropEvent:
    return QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_eta_text() -> None:
    assert eta_text(10.0, None) is None
    assert eta_text(10.0, 0.01) is None
    assert eta_text(10.0, 0.5) == "quedan ~0:10"


def test_choose_invalid_video_shows_inline_error(config: AppConfig, monkeypatch, qapp) -> None:
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    def boom(cfg: AppConfig, path: Path) -> Path:
        raise InputValidationError("video inválido")

    monkeypatch.setattr(composition, "validated_video", boom)
    page = ProcessPage(_session(config))
    page.choose_video(VIDEO)

    assert warnings == []
    assert page._video is None
    assert page._idle._error_label.text() == "video inválido"
    assert page._idle._error_label.isHidden() is False
    assert page._idle._details.isHidden() is True
    assert page._stack.currentWidget() is page._idle


def test_choose_valid_video_shows_name_and_profiles(config: AppConfig, monkeypatch, qapp) -> None:
    monkeypatch.setattr(composition, "validated_video", lambda cfg, path: path)
    page = ProcessPage(_session(config))
    page.choose_video(VIDEO)

    assert page._video == VIDEO
    assert page._idle._name_label.text() == "camion.mp4"
    assert "/" not in page._idle._name_label.text()
    assert page._idle._details.isHidden() is False
    assert list(page._idle._radios) == list(config.profiles)
    assert [radio.text() for radio in page._idle._radios.values()] == [
        profile_label(name) for name in config.profiles
    ]
    default = config.profile(None)[0]
    assert page._idle._radios[default].isChecked() is True
    assert page._idle.selected_profile() == default


def _drag_accepted(idle: IdleView, mime: QMimeData) -> bool:
    event = _drag_event(mime)
    idle.dragEnterEvent(event)
    return event.isAccepted()


def _drop_accepted(idle: IdleView, mime: QMimeData) -> bool:
    event = _drop_event(mime)
    idle.dropEvent(event)
    return event.isAccepted()


def test_drop_accepts_single_allowed_file_only(config: AppConfig, monkeypatch, qapp) -> None:
    monkeypatch.setattr(composition, "validated_video", lambda cfg, path: path)
    page = ProcessPage(_session(config))
    idle = page._idle
    allowed = VIDEO.with_suffix(config.input.allowed_extensions[0])
    refused = VIDEO.with_suffix(".txt")
    two_files = _mime(allowed, allowed.with_name("otro.mp4"))

    assert _drag_accepted(idle, two_files) is False
    assert _drop_accepted(idle, two_files) is False
    assert _drag_accepted(idle, _mime(refused)) is False
    assert page._video is None

    assert _drag_accepted(idle, _mime(allowed)) is True
    assert _drop_accepted(idle, _mime(allowed)) is True
    assert page._video == allowed


def test_start_switches_to_running_and_emits_busy(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch, session, _BlockingUseCase())
    page = ProcessPage(session)
    busy: list[bool] = []
    page.busy_changed.connect(busy.append)
    page._video = VIDEO

    page.start()

    assert page.is_busy() is True
    assert busy == [True]
    assert page._stack.currentWidget() is page._running
    assert page._running._title.text() == "Procesando camion.mp4"
    page.cancel()
    assert page._running._cancel_button.isEnabled() is False
    page.wait_for_worker()


def test_success_shows_summary_and_review_button(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    stats = RunStats(10, 8, 3, 2, 3, 1, 500, 60_000)
    _patch_processing(monkeypatch, session, _ImmediateUseCase(RunResult(7, stats)))
    page = ProcessPage(session)
    requested: list[object] = []
    page.review_requested.connect(requested.append)
    page._video = VIDEO

    _start_and_wait(page)

    assert page.is_busy() is False
    assert page._stack.currentWidget() is page._done
    assert page._done._title.text() == "Listo: 5 placas encontradas"
    assert page._done._summary.text() == (
        "2 confirmadas automáticamente · 3 por revisar · 1 vehículos sin placa legible"
    )
    assert page._done._review_button.text() == "Revisar 3 placas pendientes"
    page._done._review_button.click()
    assert requested == [7]


def test_cancel_shows_cancelled_summary(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch, session, _BlockingUseCase())
    page = ProcessPage(session)
    page._video = VIDEO
    loop = QEventLoop()
    page.run_finished.connect(loop.quit)
    QTimer.singleShot(WAIT_MS, loop.quit)

    page.start()
    page.cancel()
    loop.exec()
    page.wait_for_worker()

    assert page._stack.currentWidget() is page._done
    assert page._done._title.text() == "Procesamiento cancelado"
    assert page._done._summary.text() == "Las placas encontradas hasta ahora se guardaron."
    assert page._done._review_button.text() == "Ver lecturas"

    page._done._restart_button.click()
    assert page._stack.currentWidget() is page._idle
    assert page._video is None


def test_failure_returns_to_idle_with_error(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _patch_processing(monkeypatch, session, _FailingUseCase())
    monkeypatch.setattr(composition, "validated_video", lambda cfg, path: path)
    page = ProcessPage(session)
    page.choose_video(VIDEO)

    _start_and_wait(page)

    assert page._stack.currentWidget() is page._idle
    assert page._idle._error_label.text() == "video dañado"
    assert page._idle._error_label.isHidden() is False
    assert page._idle._details.isHidden() is False
    assert page._video == VIDEO


def _tracked_page(
    config: AppConfig, monkeypatch
) -> tuple[ProcessPage, GuiSession, int, list[object], _Clock]:
    """Crea la página con una corrida en curso y cuenta las consultas de la galería."""
    clock = _Clock()
    monkeypatch.setattr(page_module, "_monotonic", clock)
    session = _session(config)
    page = ProcessPage(session)
    run_id = session.repository.start_run(RunStart("a" * 64, "calle_lenta", VIDEO_INFO, CREATED_AT))
    session.repository.save_sighting(_sighting(run_id, "ABC123", ReviewStatus.CONFIRMED))
    queries: list[object] = []
    original = session.repository.search_sightings
    monkeypatch.setattr(
        session.repository,
        "search_sightings",
        lambda query, limit, offset: queries.append(query) or original(query, limit, offset),
    )
    return page, session, run_id, queries, clock


def test_live_grid_refreshes_when_sightings_increase(config: AppConfig, monkeypatch, qapp) -> None:
    page, session, run_id, queries, clock = _tracked_page(config, monkeypatch)

    page._on_progress(ProgressUpdate(10, 5, 1000, 60_000, 1))
    assert len(queries) == 1
    assert len(page._running._grid.ids()) == 1

    page._on_progress(ProgressUpdate(10, 5, 1200, 60_000, 1))
    assert len(queries) == 1

    session.repository.save_sighting(_sighting(run_id, "XYZ789", ReviewStatus.CONFIRMED))
    session.repository.save_sighting(_sighting(run_id, "QWE456", ReviewStatus.CONFIRMED))
    page._on_progress(ProgressUpdate(10, 6, 1400, 60_000, 2))
    assert len(queries) == 1
    assert len(page._running._grid.ids()) == 1

    clock.value = 2.0
    page._on_progress(ProgressUpdate(10, 7, 1600, 60_000, 3))
    assert len(queries) == 2
    assert len(page._running._grid.ids()) == 3
