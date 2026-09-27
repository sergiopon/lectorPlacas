from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.gui import card_grid
from lector_placas.gui.card_grid import CardGrid, columns_for_width

CREATED_AT = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)


def _record(sighting_id: int, plate_text: str = "ABC123") -> SightingRecord:
    return SightingRecord(
        sighting_id=sighting_id,
        run_id=1,
        track_id=sighting_id,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type=VehicleType.CAR,
        ocr_text=plate_text,
        plate_text=plate_text,
        confidence=0.5,
        agreement=0.5,
        num_readings=2,
        status=ReviewStatus.UNVERIFIED,
        reasons=(),
        format_ids=(),
        crop_ref=None,
        created_at=CREATED_AT,
        reviewed_at=None,
    )


def _grid_with(ids: list[int]) -> CardGrid:
    grid = CardGrid()
    grid.set_records([_record(sighting_id) for sighting_id in ids], {})
    return grid


def test_columns_for_width() -> None:
    assert columns_for_width(0) == 1
    assert columns_for_width(272) == 1
    assert columns_for_width(544) == 2
    assert columns_for_width(900) == 3


def test_empty_grid_shows_empty_state(qapp) -> None:
    grid = CardGrid()
    assert grid._stack.currentWidget() is grid._empty
    assert grid._empty._title_label.text() == "Nada por aquí"
    assert grid._empty._hint_label.text() == ""


def test_set_empty_message_changes_texts(qapp) -> None:
    grid = CardGrid()
    grid.set_empty_message("Sin resultados", "Ajuste el filtro")
    assert grid._empty._title_label.text() == "Sin resultados"
    assert grid._empty._hint_label.text() == "Ajuste el filtro"


def test_set_records_keeps_order_and_append_adds(qapp) -> None:
    grid = _grid_with([1, 2, 3])
    assert grid.ids() == [1, 2, 3]
    assert grid._stack.currentWidget() is grid._container
    grid.select(2)
    grid.set_records([_record(1), _record(2), _record(3)], {})
    assert grid.ids() == [1, 2, 3]
    assert grid.selected_id() == 2
    grid.append_records([_record(4)], {})
    assert grid.ids() == [1, 2, 3, 4]


def test_select_emits_once_and_marks_card(qapp) -> None:
    grid = _grid_with([1, 2, 3])
    received: list[int] = []
    grid.selection_changed.connect(received.append)
    grid.select(1)
    grid.select(1)
    assert received == [1]
    assert grid.selected_id() == 1
    assert grid._cards[1].is_selected() is True
    grid.select(2)
    assert received == [1, 2]
    assert grid._cards[1].is_selected() is False
    assert grid._cards[2].is_selected() is True


def test_select_none_and_unknown_id_clear_without_emitting(qapp) -> None:
    grid = _grid_with([1, 2])
    received: list[int] = []
    grid.selection_changed.connect(received.append)
    grid.select(1)
    received.clear()
    grid.select(None)
    assert grid.selected_id() is None
    assert received == []
    grid.select(99)
    assert grid.selected_id() is None
    assert received == []


def test_keyboard_navigation(qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_grid, "columns_for_width", lambda width: 3)
    grid = _grid_with([1, 2, 3, 4, 5])
    grid.resize(900, 600)
    grid.show()
    qapp.processEvents()

    QTest.keyClick(grid, Qt.Key.Key_Right)
    assert grid.selected_id() == 1
    QTest.keyClick(grid, Qt.Key.Key_Right)
    assert grid.selected_id() == 2
    QTest.keyClick(grid, Qt.Key.Key_Down)
    assert grid.selected_id() == 5
    QTest.keyClick(grid, Qt.Key.Key_Left)
    assert grid.selected_id() == 4
    grid.close()


def test_keyboard_navigation_without_selection_selects_first(qapp) -> None:
    grid = _grid_with([1, 2, 3])
    grid.show()
    QTest.keyClick(grid, Qt.Key.Key_Down)
    assert grid.selected_id() == 1
    grid.close()


def test_remove_and_next_id(qapp) -> None:
    grid = _grid_with([1, 2, 3])
    assert grid.next_id(1) == 2
    assert grid.next_id(3) == 2
    assert grid.next_id(99) is None
    received: list[int] = []
    grid.selection_changed.connect(received.append)
    grid.select(2)
    received.clear()
    grid.remove(2)
    assert grid.ids() == [1, 3]
    assert grid.selected_id() is None
    assert received == []
    grid.remove(99)
    assert grid.ids() == [1, 3]


def test_update_record_updates_card(qapp) -> None:
    grid = _grid_with([1, 2])
    grid.update_record(_record(2, plate_text="XYZ98K"))
    assert grid._cards[2]._plate_label.text() == "XYZ 98K"
    grid.update_record(_record(99, plate_text="ABC12D"))
    assert grid.ids() == [1, 2]
