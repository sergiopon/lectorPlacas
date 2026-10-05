"""Tests de aceptación para `CropQuality`."""

from __future__ import annotations

import pytest

from lector_placas.domain.entities import CropQuality
from lector_placas.domain.errors import InvalidEntityError


def test_valid_crop_quality() -> None:
    """Una CropQuality válida se crea sin errores."""
    quality = CropQuality(100, 30, 12.5, 40.0)
    assert quality.plate_width_px == 100
    assert quality.plate_height_px == 30
    assert quality.sharpness == 12.5
    assert quality.contrast == 40.0


@pytest.mark.parametrize(
    "width,height,sharpness,contrast",
    [
        (0, 30, 12.5, 40.0),  # width = 0
        (100, 0, 12.5, 40.0),  # height = 0
        (100, 30, -1.0, 40.0),  # sharpness < 0
        (100, 30, 12.5, -0.5),  # contrast < 0
        (100, 30, float("nan"), 40.0),  # sharpness is NaN
        (100, 30, 12.5, float("inf")),  # contrast is inf
    ],
)
def test_invalid_crop_quality(width: int, height: int, sharpness: float, contrast: float) -> None:
    """CropQuality rechaza valores inválidos."""
    with pytest.raises(InvalidEntityError):
        CropQuality(width, height, sharpness, contrast)


def test_sighting_record_duplicate_of() -> None:
    """SightingRecord valida que duplicate_of sea válido."""
    from lector_placas.domain.entities import ReviewStatus, SightingRecord

    # duplicate_of = sighting_id: inválido
    with pytest.raises(InvalidEntityError):
        SightingRecord(
            sighting_id=5,
            run_id=1,
            track_id=1,
            first_seen_ms=0,
            last_seen_ms=1000,
            vehicle_type="car",
            ocr_text="ABC123",
            plate_text="ABC123",
            confidence=0.9,
            agreement=0.8,
            num_readings=3,
            status=ReviewStatus.CONFIRMED,
            reasons=(),
            format_ids=(),
            crop_ref=None,
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            reviewed_at=None,
            quality=None,
            duplicate_of=5,
        )

    # duplicate_of = 0: inválido
    with pytest.raises(InvalidEntityError):
        SightingRecord(
            sighting_id=5,
            run_id=1,
            track_id=1,
            first_seen_ms=0,
            last_seen_ms=1000,
            vehicle_type="car",
            ocr_text="ABC123",
            plate_text="ABC123",
            confidence=0.9,
            agreement=0.8,
            num_readings=3,
            status=ReviewStatus.CONFIRMED,
            reasons=(),
            format_ids=(),
            crop_ref=None,
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            reviewed_at=None,
            quality=None,
            duplicate_of=0,
        )

    # duplicate_of = 3: válido
    record = SightingRecord(
        sighting_id=5,
        run_id=1,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type="car",
        ocr_text="ABC123",
        plate_text="ABC123",
        confidence=0.9,
        agreement=0.8,
        num_readings=3,
        status=ReviewStatus.CONFIRMED,
        reasons=(),
        format_ids=(),
        crop_ref=None,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        reviewed_at=None,
        quality=None,
        duplicate_of=3,
    )
    assert record.duplicate_of == 3
