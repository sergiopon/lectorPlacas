from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.domain.errors import InvalidEntityError
from lector_placas.gui.images import bgr_to_pixmap
from lector_placas.gui.plate_card import NO_IMAGE_TEXT, PlateCard

CREATED_AT = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)


def _record(
    sighting_id: int = 1,
    plate_text: str = "ABC123",
    status: ReviewStatus = ReviewStatus.UNVERIFIED,
    first_seen_ms: int = 5000,
    num_readings: int = 4,
    vehicle_type: VehicleType = VehicleType.CAR,
) -> SightingRecord:
    return SightingRecord(
        sighting_id=sighting_id,
        run_id=1,
        track_id=1,
        first_seen_ms=first_seen_ms,
        last_seen_ms=first_seen_ms + 1000,
        vehicle_type=vehicle_type,
        ocr_text=plate_text,
        plate_text=plate_text,
        confidence=0.5,
        agreement=0.5,
        num_readings=num_readings,
        status=status,
        reasons=(),
        format_ids=(),
        crop_ref=None,
        created_at=CREATED_AT,
        reviewed_at=None,
    )


def _crop() -> QPixmap:
    return bgr_to_pixmap(np.zeros((10, 30, 3), dtype=np.uint8), 244, 84)


def test_card_shows_formatted_plate_badge_and_meta(qapp) -> None:
    card = PlateCard(_record(), None)
    assert card._plate_label.objectName() == "PlateText"
    assert card._plate_label.text() == "ABC 123"
    assert card._status_label.text() == "Por revisar"
    assert card._meta_label.text() == "Carro · 0:05 · 4 lecturas"


def test_card_without_crop_shows_placeholder(qapp) -> None:
    card = PlateCard(_record(), None)
    assert card._crop_label.text() == NO_IMAGE_TEXT
    assert card._crop_label.pixmap().isNull()


def test_click_emits_sighting_id(qapp) -> None:
    card = PlateCard(_record(sighting_id=7), _crop())
    received: list[int] = []
    card.clicked.connect(received.append)
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    assert received == [7]


def test_selected_property_toggles(qapp) -> None:
    card = PlateCard(_record(), None)
    assert card.is_selected() is False
    card.set_selected(True)
    assert card.is_selected() is True
    assert card.property("selected") == "true"
    card.set_selected(False)
    assert card.is_selected() is False
    assert card.property("selected") == "false"


def test_update_record_changes_plate_and_badge(qapp) -> None:
    card = PlateCard(_record(), None)
    card.update_record(_record(plate_text="XYZ98K", status=ReviewStatus.CONFIRMED))
    assert card._plate_label.text() == "XYZ 98K"
    assert card._status_label.text() == "Confirmada"


def test_update_record_rejects_other_id(qapp) -> None:
    card = PlateCard(_record(sighting_id=1), None)
    with pytest.raises(InvalidEntityError):
        card.update_record(_record(sighting_id=2))
    assert card.sighting_id() == 1
