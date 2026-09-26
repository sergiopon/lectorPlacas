from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from lector_placas.domain.entities import (
    BoundingBox,
    ConsolidatedPlate,
    OcrResult,
    PlateDetection,
    PlateFormat,
    PlateReading,
    ReviewStatus,
    Sighting,
    SightingRecord,
    TrackedVehicle,
    UnverifiedReason,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import (
    CropNotFoundError,
    CropStoreError,
    DomainError,
    InputValidationError,
    InvalidBoundingBoxError,
    InvalidConfidenceError,
    InvalidEntityError,
    InvalidPlateTextError,
    LectorPlacasError,
    PlateFormatCatalogError,
    RepositoryError,
    SightingNotFoundError,
    UnsafePathError,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def make_box() -> BoundingBox:
    return BoundingBox(10.0, 20.0, 110.0, 70.0)


def make_plate(**overrides: object) -> ConsolidatedPlate:
    values: dict[str, object] = dict(
        text="ABC123",
        confidence=0.95,
        agreement=1.0,
        num_readings=3,
        status=ReviewStatus.CONFIRMED,
        reasons=(),
        format_ids=("co_particular_publico",),
    )
    values.update(overrides)
    return ConsolidatedPlate(**values)  # type: ignore[arg-type]


def test_error_hierarchy() -> None:
    assert issubclass(DomainError, LectorPlacasError)
    assert issubclass(InvalidBoundingBoxError, DomainError)
    assert issubclass(UnsafePathError, InputValidationError)
    assert issubclass(SightingNotFoundError, RepositoryError)
    assert issubclass(CropNotFoundError, CropStoreError)


def test_bounding_box_properties() -> None:
    box = make_box()
    assert (box.width, box.height, box.area) == (100.0, 50.0, 5000.0)


@pytest.mark.parametrize(
    "coords",
    [
        (0, 0, 0, 10),
        (0, 0, 10, 0),
        (-1, 0, 10, 10),
        (0, -1, 10, 10),
        (5, 0, 4, 10),
        (0, 0, math.nan, 10),
        (0, 0, math.inf, 10),
    ],
)
def test_bounding_box_rejects_invalid(coords: tuple[float, float, float, float]) -> None:
    with pytest.raises(InvalidBoundingBoxError):
        BoundingBox(*coords)


def test_bounding_box_translate() -> None:
    assert make_box().translate(5, -10) == BoundingBox(15.0, 10.0, 115.0, 60.0)


def test_bounding_box_clip_inside_and_outside() -> None:
    assert BoundingBox(10, 10, 300, 300).clip(200, 100) == BoundingBox(10, 10, 200, 100)
    assert BoundingBox(250, 10, 300, 50).clip(200, 100) is None


def test_bounding_box_expand_is_clipped() -> None:
    expanded = BoundingBox(10, 10, 110, 60).expand(0.1, 115, 1000)
    assert expanded == BoundingBox(0.0, 5.0, 115.0, 65.0)


def test_bounding_box_expand_rejects_bad_ratio() -> None:
    with pytest.raises(InvalidBoundingBoxError):
        make_box().expand(1.5, 100, 100)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, math.nan])
def test_detection_rejects_bad_confidence(confidence: float) -> None:
    with pytest.raises(InvalidConfidenceError):
        VehicleDetection(make_box(), confidence, VehicleType.CAR)
    with pytest.raises(InvalidConfidenceError):
        PlateDetection(make_box(), confidence)


def test_tracked_vehicle_rejects_negative_id() -> None:
    with pytest.raises(InvalidEntityError):
        TrackedVehicle(-1, make_box(), 0.9, VehicleType.CAR)


def test_ocr_result_allows_empty_text() -> None:
    assert OcrResult("", ()).text == ""


@pytest.mark.parametrize("text", ["abc123", "ABC-12", "ABCDEFGHIJK"])
def test_ocr_result_rejects_bad_text(text: str) -> None:
    with pytest.raises(InvalidPlateTextError):
        OcrResult(text, tuple(0.9 for _ in text))


def test_ocr_result_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidEntityError):
        OcrResult("ABC", (0.9, 0.9))


def test_plate_reading_mean_confidence() -> None:
    reading = PlateReading(1, 2, 3, "AB", (0.5, 1.0), make_box(), 0.8, 10.0)
    assert reading.mean_confidence == pytest.approx(0.75)


def test_plate_reading_rejects_empty_text_and_negative_quality() -> None:
    with pytest.raises(InvalidPlateTextError):
        PlateReading(1, 2, 3, "", (), make_box(), 0.8, 1.0)
    with pytest.raises(InvalidEntityError):
        PlateReading(1, 2, 3, "AB", (0.5, 0.5), make_box(), 0.8, -1.0)


def test_plate_format_matches_full_text() -> None:
    fmt = PlateFormat(
        "co_moto",
        "Moto",
        "LLLDDL",
        "^[A-Z]{3}[0-9]{2}[A-Z]$",
        True,
        frozenset({VehicleType.MOTORCYCLE}),
        "Res. 4923/1994",
    )
    assert fmt.matches("XYZ98K")
    assert not fmt.matches("XYZ98KK")


@pytest.mark.parametrize(
    "field,value",
    [
        ("format_id", "Co-Moto"),
        ("pattern", "LLX"),
        ("regex", "[A-Z"),
        ("category", " "),
        ("source", ""),
        ("vehicle_types", frozenset()),
    ],
)
def test_plate_format_rejects_invalid(field: str, value: object) -> None:
    values: dict[str, object] = dict(
        format_id="co_moto",
        category="Moto",
        pattern="LLLDDL",
        regex="^[A-Z]{3}$",
        verified=True,
        vehicle_types=frozenset({VehicleType.MOTORCYCLE}),
        source="fuente",
    )
    values[field] = value
    with pytest.raises(PlateFormatCatalogError):
        PlateFormat(**values)  # type: ignore[arg-type]


def test_consolidated_plate_status_rules() -> None:
    with pytest.raises(InvalidEntityError):
        make_plate(reasons=(UnverifiedReason.LOW_CONFIDENCE,))
    with pytest.raises(InvalidEntityError):
        make_plate(status=ReviewStatus.UNVERIFIED, reasons=())
    with pytest.raises(InvalidEntityError):
        make_plate(status=ReviewStatus.REJECTED)
    with pytest.raises(InvalidEntityError):
        make_plate(
            status=ReviewStatus.UNVERIFIED,
            reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_CONFIDENCE),
        )
    ok = make_plate(status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.LOW_AGREEMENT,))
    assert ok.status is ReviewStatus.UNVERIFIED


def test_sighting_requires_utc_and_valid_times() -> None:
    plate = make_plate()
    Sighting(1, 0, 100, 200, VehicleType.CAR, plate, "0" * 32, NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 300, 200, VehicleType.CAR, plate, None, NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 100, 200, VehicleType.CAR, plate, None, NOW.replace(tzinfo=None))
    with pytest.raises(InvalidEntityError):
        Sighting(
            1,
            0,
            100,
            200,
            VehicleType.CAR,
            plate,
            None,
            NOW.astimezone(timezone(timedelta(hours=-5))),
        )
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 100, 200, VehicleType.CAR, plate, "XYZ", NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(0, 0, 100, 200, VehicleType.CAR, plate, None, NOW)


def test_sighting_record_validates_texts() -> None:
    SightingRecord(
        1,
        1,
        0,
        0,
        10,
        VehicleType.CAR,
        "ABC123",
        "ABC128",
        0.9,
        0.8,
        3,
        ReviewStatus.CORRECTED,
        (),
        ("co_particular_publico",),
        None,
        NOW,
        NOW,
    )
    with pytest.raises(InvalidPlateTextError):
        SightingRecord(
            1,
            1,
            0,
            0,
            10,
            VehicleType.CAR,
            "abc",
            "ABC128",
            0.9,
            0.8,
            3,
            ReviewStatus.CORRECTED,
            (),
            (),
            None,
            NOW,
            None,
        )
