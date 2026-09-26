from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lector_placas.domain.entities import (
    BoundingBox,
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    VehicleType,
)
from lector_placas.domain.errors import InvalidBoundingBoxError


def test_expand_zero_returns_same_box() -> None:
    box = BoundingBox(10.5, 20.25, 30.0, 40.0)
    assert box.expand(0.0, 100, 100) == box


def test_clip_box_touching_frame_edge_is_kept() -> None:
    assert BoundingBox(90, 90, 100, 100).clip(100, 100) == BoundingBox(90, 90, 100, 100)


def test_clip_box_starting_at_frame_edge_is_empty() -> None:
    assert BoundingBox(100, 10, 120, 20).clip(100, 100) is None


def test_translate_to_negative_raises() -> None:
    with pytest.raises(InvalidBoundingBoxError):
        BoundingBox(5, 5, 10, 10).translate(-6, 0)


def test_sighting_accepts_microseconds() -> None:
    plate = ConsolidatedPlate("ABC123", 0.9, 1.0, 3, ReviewStatus.CONFIRMED, (), ())
    at = datetime(2026, 9, 26, 12, 0, 0, 123456, tzinfo=UTC)
    assert Sighting(1, 0, 0, 0, VehicleType.CAR, plate, None, at).created_at.microsecond == 123456


def test_ocr_text_boundary_lengths() -> None:
    from lector_placas.domain.entities import OcrResult
    from lector_placas.domain.errors import InvalidPlateTextError

    assert OcrResult("A" * 10, (0.5,) * 10).text == "A" * 10
    with pytest.raises(InvalidPlateTextError):
        OcrResult("A" * 11, (0.5,) * 11)
