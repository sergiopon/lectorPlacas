from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import RepositoryError
from lector_placas.gui.readings_page import PAGE_SIZE, ReadingsPage
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
VIDEO = VideoInfo(
    width=640,
    height=480,
    rotation_deg=0,
    duration_ms=60_000,
    average_fps=30.0,
    codec="h264",
)
NO_IMAGE = "sin imagen"


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


def _start_run(session: GuiSession, profile: str = "calle_lenta") -> int:
    return session.repository.start_run(RunStart("a" * 64, profile, VIDEO, CREATED_AT))


def _add(
    session: GuiSession,
    plate_text: str,
    run_id: int = 1,
    status: ReviewStatus = ReviewStatus.UNVERIFIED,
    crop_ref: str | None = None,
) -> int:
    reasons = () if status is ReviewStatus.CONFIRMED else (UnverifiedReason.INSUFFICIENT_READINGS,)
    plate = ConsolidatedPlate(
        text=plate_text,
        confidence=0.5,
        agreement=0.5,
        num_readings=2,
        status=status,
        reasons=reasons,
        format_ids=(),
    )
    sighting = Sighting(
        run_id=run_id,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type=VehicleType.CAR,
        plate=plate,
        crop_ref=crop_ref,
        created_at=CREATED_AT,
    )
    return session.repository.save_sighting(sighting)


def _seed_pending(session: GuiSession, count: int) -> list[int]:
    return [_add(session, f"AAA{index:03d}") for index in range(count)]


@pytest.fixture
def show_page(qapp):
    """Muestra una página y la cierra al terminar (una ventana abierta bloquea el próximo modal)."""
    opened: list[ReadingsPage] = []

    def open_page(page: ReadingsPage) -> ReadingsPage:
        page.show()
        opened.append(page)
        return page

    yield open_page
    for page in opened:
        page.close()


def test_initial_filter_is_pending_when_there_are_pending(config: AppConfig, qapp) -> None:
    session = _session(config)
    _seed_pending(session, 2)

    page = ReadingsPage(session)

    assert page._filters.status() is ReviewStatus.UNVERIFIED
    assert page.pending_count() == 2
    assert len(page._grid.ids()) == 2


def test_initial_filter_is_all_when_there_are_no_pending(config: AppConfig, qapp) -> None:
    session = _session(config)
    _add(session, "BBB222", status=ReviewStatus.CONFIRMED)

    page = ReadingsPage(session)

    assert page._filters.status() is None
    assert page.pending_count() == 0


def test_cards_have_crops_or_placeholder(config: AppConfig, qapp) -> None:
    session = _session(config)
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    real_ref = session.crop_store.save(image)
    with_crop = _add(session, "AAA111", crop_ref=real_ref)
    purged = _add(session, "BBB222", crop_ref="0" * 32)
    without_crop = _add(session, "CCC333", crop_ref=None)

    page = ReadingsPage(session)
    cards = page._grid._cards

    assert cards[with_crop]._crop_label.pixmap().isNull() is False
    assert cards[purged]._crop_label.pixmap().isNull() is True
    assert cards[purged]._crop_label.text() == NO_IMAGE
    assert cards[without_crop]._crop_label.text() == NO_IMAGE


def test_filter_change_reloads_first_page_and_counts(config: AppConfig, qapp) -> None:
    session = _session(config)
    pending_ids = _seed_pending(session, 3)
    confirmed_id = _add(session, "BBB222", status=ReviewStatus.CONFIRMED)
    page = ReadingsPage(session)
    assert page._grid.ids() == sorted(pending_ids, reverse=True)

    page._filters._buttons[ReviewStatus.CONFIRMED].click()

    assert page._filters.status() is ReviewStatus.CONFIRMED
    assert page._grid.ids() == [confirmed_id]
    assert page._grid.selected_id() is None
    assert page._panel._record is None
    assert page._filters._buttons[ReviewStatus.CONFIRMED].text() == "Confirmadas (1)"
    assert page._filters._buttons[ReviewStatus.UNVERIFIED].text() == "Por revisar (3)"


def test_show_more_appends_next_page(config: AppConfig, show_page, qapp) -> None:
    session = _session(config)
    _seed_pending(session, 130)
    page = show_page(ReadingsPage(session))
    qapp.processEvents()

    assert len(page._grid.ids()) == PAGE_SIZE
    assert page._more_button.isVisible() is True

    page._more_button.click()
    assert len(page._grid.ids()) == 2 * PAGE_SIZE
    assert page._more_button.isVisible() is True

    page._more_button.click()
    assert len(page._grid.ids()) == 130
    assert page._more_button.isVisible() is False


def test_decision_removes_card_from_pending_and_selects_next(config: AppConfig, qapp) -> None:
    session = _session(config)
    _seed_pending(session, 3)
    page = ReadingsPage(session)
    events: list[int] = []
    page.pending_changed.connect(events.append)
    order = page._grid.ids()

    page._grid.select(order[0])
    assert page._panel._record.sighting_id == order[0]
    page._panel.confirm()

    assert order[0] not in page._grid.ids()
    assert page._grid.selected_id() == order[1]
    assert page._panel._record.sighting_id == order[1]
    assert page.pending_count() == 2
    assert events[-1] == 2
    assert page._filters._buttons[ReviewStatus.UNVERIFIED].text() == "Por revisar (2)"
    assert session.repository.get_sighting(order[0]).status is ReviewStatus.CONFIRMED


def test_decision_in_all_filter_updates_card_in_place(config: AppConfig, qapp) -> None:
    session = _session(config)
    _seed_pending(session, 3)
    page = ReadingsPage(session)
    page._filters.set_status(None)
    page.reload()
    order = page._grid.ids()

    page._grid.select(order[0])
    page._panel.confirm()

    assert order[0] in page._grid.ids()
    assert page._grid._cards[order[0]]._status_label.text() == "Confirmada"
    assert page._grid.selected_id() == order[1]


def test_shortcuts_confirm_and_skip(config: AppConfig, show_page, qapp) -> None:
    session = _session(config)
    _seed_pending(session, 3)
    page = show_page(ReadingsPage(session))
    page.activateWindow()
    qapp.processEvents()
    order = page._grid.ids()
    page._grid.select(order[0])

    QTest.keyClick(page, Qt.Key.Key_C)
    assert (order[0] in page._grid.ids(), page._grid.selected_id()) == (False, order[1])

    QTest.keyClick(page, Qt.Key.Key_S)
    assert page._grid.selected_id() == order[2]
    assert session.repository.get_sighting(order[1]).status is ReviewStatus.UNVERIFIED

    QTest.keyClick(page, Qt.Key.Key_E)
    assert page._panel.is_editing() is True
    selected = page._grid.selected_id()
    QTest.keyClick(page, Qt.Key.Key_C)
    assert (page._panel.is_editing(), page._grid.selected_id()) == (True, selected)


def test_busy_blocks_decisions(config: AppConfig, qapp) -> None:
    session = _session(config)
    ids = _seed_pending(session, 2)
    page = ReadingsPage(session)
    page._grid.select(ids[0])

    page.set_busy(True)
    assert all(not button.isEnabled() for button in page._panel._buttons)
    page._panel.confirm()
    assert session.repository.get_sighting(ids[0]).status is ReviewStatus.UNVERIFIED
    assert len(page._grid.ids()) == 2

    page.set_busy(False)
    assert all(button.isEnabled() for button in page._panel._buttons)
    page._panel.confirm()
    assert session.repository.get_sighting(ids[0]).status is ReviewStatus.CONFIRMED


def test_empty_messages(config: AppConfig, qapp) -> None:
    session = _session(config)
    empty_page = ReadingsPage(session)
    assert empty_page._grid._empty._title_label.text() == "Aún no hay lecturas"
    assert (
        empty_page._grid._empty._hint_label.text()
        == "Procesa un video para ver aquí las placas encontradas."
    )

    _add(session, "BBB222", status=ReviewStatus.CONFIRMED)
    page = ReadingsPage(session)
    page._filters.set_status(ReviewStatus.UNVERIFIED)
    page.reload()
    assert page._grid._empty._title_label.text() == "¡Todo revisado!"
    assert page._grid._empty._hint_label.text() == "No quedan placas pendientes."

    page._filters._search.setText("ZZZ999")
    QTest.qWait(400)
    assert page._grid._empty._title_label.text() == "Sin resultados"
    assert page._grid._empty._hint_label.text() == "Prueba con otra placa o quita los filtros."


def test_show_run_sets_filters_and_selects_first(config: AppConfig, qapp) -> None:
    session = _session(config)
    run_one = _start_run(session, "calle_lenta")
    run_two = _start_run(session, "parqueadero")
    _add(session, "AAA111", run_id=run_one)
    _add(session, "BBB222", run_id=run_two)
    _add(session, "CCC333", run_id=run_two)
    page = ReadingsPage(session)

    page.show_run(run_two, ReviewStatus.UNVERIFIED)

    assert page._filters.run_id() == run_two
    assert page._filters.status() is ReviewStatus.UNVERIFIED
    order = page._grid.ids()
    assert len(order) == 2
    assert page._grid.selected_id() == order[0]
    assert page._panel._record.sighting_id == order[0]
    assert page._panel._record.run_id == run_two


def test_decision_error_shows_warning(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _add(session, "AAA111")
    page = ReadingsPage(session)
    page._grid.select(page._grid.ids()[0])
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    def boom(*args: object, **kwargs: object) -> None:
        raise RepositoryError("fallo de repositorio")

    monkeypatch.setattr(session.repository, "record_review", boom)
    page._panel.confirm()

    assert len(warnings) == 1
    assert warnings[0][2] == "fallo de repositorio"
    assert len(page._grid.ids()) == 1
