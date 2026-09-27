from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.gui.review_dialog import ReviewDialog
from lector_placas.gui.session import GuiSession
from lector_placas.gui.sightings_detail import CROP_PURGED_TEXT, NO_CROP_TEXT
from lector_placas.gui.sightings_tab import (
    INVALID_RANGE_MESSAGE,
    PAGE_SIZE,
    SIGHTING_COLUMNS,
    SightingsTab,
    SightingsTableModel,
)
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

CREATED_AT = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


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


def _add_sighting(
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
        num_readings=1,
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


def _row_for(tab: SightingsTab, sighting_id: int) -> int:
    for row in range(tab._model.rowCount()):
        if tab._model.record_at(row).sighting_id == sighting_id:
            return row
    raise AssertionError(f"sighting_id {sighting_id} no está en la tabla")


def test_initial_search_lists_all_descending(config: AppConfig, qapp) -> None:
    session = _session(config)
    ids = [_add_sighting(session, plate) for plate in ("AAA111", "BBB222", "CCC333")]
    tab = SightingsTab(session)
    assert tab._model.rowCount() == 3
    shown_ids = [tab._model.record_at(row).sighting_id for row in range(3)]
    assert shown_ids == sorted(ids, reverse=True)
    assert tab._page_label.text() == "página 1 de 1 (3 avistamientos)"


def test_filters_build_query(config: AppConfig, qapp) -> None:
    tab = SightingsTab(_session(config))
    filters = tab._filters
    filters._status_combo.setCurrentIndex(1)  # primer estado tras "Todos"
    filters._plate_edit.setText("abc123")
    filters._run_spin.setValue(7)
    filters._from_check.setChecked(True)
    filters._from_date.setDate(QDate(2026, 9, 10))
    filters._to_check.setChecked(True)
    filters._to_date.setDate(QDate(2026, 9, 15))

    query = tab.current_query()

    assert isinstance(query, SightingQuery)
    assert query.status is ReviewStatus.CONFIRMED
    assert query.plate_prefix == "ABC123"
    assert query.run_id == 7
    assert query.created_from == datetime(2026, 9, 10, 0, 0, 0).astimezone()
    assert query.created_to == datetime(2026, 9, 16, 0, 0, 0).astimezone()


def test_inverted_date_range_warns(config: AppConfig, monkeypatch, qapp) -> None:
    tab = SightingsTab(_session(config))
    filters = tab._filters
    filters._from_check.setChecked(True)
    filters._from_date.setDate(QDate(2026, 9, 20))
    filters._to_check.setChecked(True)
    filters._to_date.setDate(QDate(2026, 9, 10))
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    tab.search()

    assert len(warnings) == 1
    assert warnings[0][2] == INVALID_RANGE_MESSAGE


def test_pagination_next_previous(config: AppConfig, qapp) -> None:
    session = _session(config)
    for index in range(250):
        _add_sighting(session, f"AAA{index % 10}{index % 10}{index % 10}")
    tab = SightingsTab(session)

    assert tab._model.rowCount() == PAGE_SIZE
    assert tab._prev_button.isEnabled() is False
    assert tab._next_button.isEnabled() is True

    tab._next_button.click()
    assert tab._model.rowCount() == PAGE_SIZE
    assert tab._prev_button.isEnabled() is True
    assert tab._next_button.isEnabled() is True

    tab._next_button.click()
    assert tab._model.rowCount() == 50
    assert tab._next_button.isEnabled() is False

    tab._prev_button.click()
    assert tab._model.rowCount() == PAGE_SIZE
    assert tab._next_button.isEnabled() is True


def test_detail_shows_crop_and_handles_missing(config: AppConfig, qapp) -> None:
    session = _session(config)
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    real_ref = session.crop_store.save(image)
    purged_ref = "0" * 32
    with_crop = _add_sighting(session, "AAA111", crop_ref=real_ref)
    with_purged = _add_sighting(session, "BBB222", crop_ref=purged_ref)
    without_crop = _add_sighting(session, "CCC333", crop_ref=None)
    tab = SightingsTab(session)

    tab._table.setCurrentIndex(tab._model.index(_row_for(tab, with_crop), 0))
    assert tab._detail._crop_label.pixmap().isNull() is False

    tab._table.setCurrentIndex(tab._model.index(_row_for(tab, with_purged), 0))
    assert tab._detail._crop_label.text() == CROP_PURGED_TEXT

    tab._table.setCurrentIndex(tab._model.index(_row_for(tab, without_crop), 0))
    assert tab._detail._crop_label.text() == NO_CROP_TEXT


def test_review_button_runs_review_and_refreshes(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    _add_sighting(session, "AAA111")
    _add_sighting(session, "BBB222")
    tab = SightingsTab(session)

    keys = iter([Qt.Key.Key_C, Qt.Key.Key_C])

    def fake_exec(self: ReviewDialog) -> int:
        QTest.keyClick(self, next(keys))
        return 0

    monkeypatch.setattr(ReviewDialog, "exec", fake_exec)
    infos: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args))

    tab._review_unverified_button.click()

    assert len(infos) == 1
    assert "confirmados=2" in infos[0][2]
    statuses = {record.status for record in session.repository.list_sightings(None, 10, 0)}
    assert statuses == {ReviewStatus.CONFIRMED}


def test_busy_disables_review_buttons(config: AppConfig, qapp) -> None:
    tab = SightingsTab(_session(config))
    tab.set_busy(True)
    assert tab._review_unverified_button.isEnabled() is False
    assert tab._review_confirmed_button.isEnabled() is False
    tab.set_busy(False)
    assert tab._review_unverified_button.isEnabled() is True
    assert tab._review_confirmed_button.isEnabled() is True


def test_model_formats_columns(qapp) -> None:
    model = SightingsTableModel()
    record_id = 42
    record = SightingRecord(
        sighting_id=record_id,
        run_id=3,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type=VehicleType.MOTORCYCLE,
        ocr_text="ABD123",
        plate_text="ABC123",
        confidence=0.873,
        agreement=0.9,
        num_readings=4,
        status=ReviewStatus.CORRECTED,
        reasons=(),
        format_ids=(),
        crop_ref=None,
        created_at=CREATED_AT,
        reviewed_at=CREATED_AT,
    )
    model.set_records([record])
    expected = (
        "42",
        CREATED_AT.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "3",
        "moto",
        "ABC123",
        "ABD123",
        "corregido",
        "87 %",
        "4",
        "-",
    )
    assert len(SIGHTING_COLUMNS) == len(expected)
    for column, value in enumerate(expected):
        assert model.data(model.index(0, column)) == value
