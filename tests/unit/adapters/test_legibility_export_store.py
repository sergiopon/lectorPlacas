from __future__ import annotations

import csv
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.adapters.export.legibility_export_store import (
    ANNOTATIONS_FILE,
    FilesystemLegibilityExportStore,
)
from lector_placas.application.ports import ImageBGR, LegibilityLabel, LegibilitySample
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason, VehicleType
from lector_placas.domain.errors import ExportError

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
HEADER = (
    "image_path,label,status,human_reviewed,video_group,run_id,track_id,"
    "vehicle_type,confidence,agreement,num_readings,reasons,crop_width,crop_height,"
    "plate_width_px,plate_height_px,sharpness,contrast,frame_width,frame_height"
)
REASONS = (UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.INSUFFICIENT_READINGS)
PLATES = ("ABC123", "XYZ98K")


def image() -> ImageBGR:
    img = np.zeros((10, 30, 3), np.uint8)
    img[:, :, 2] = 200
    return img


def sample(
    label: LegibilityLabel = LegibilityLabel.LEGIBLE,
    *,
    human_reviewed: bool = False,
    reasons: tuple[UnverifiedReason, ...] = (),
) -> LegibilitySample:
    return LegibilitySample(
        image=image(),
        label=label,
        status=ReviewStatus.CONFIRMED,
        human_reviewed=human_reviewed,
        video_group=1,
        run_id=1,
        track_id=0,
        vehicle_type=VehicleType.CAR,
        confidence=0.9512,
        agreement=1.0,
        num_readings=3,
        reasons=reasons,
    )


def test_writes_private_dataset(tmp_path: Path) -> None:
    store = FilesystemLegibilityExportStore(tmp_path / "own")
    path = store.write_samples([sample(human_reviewed=True, reasons=REASONS)], T0)

    assert path.name == "legibility-20260926T120000Z"
    text = (path / ANNOTATIONS_FILE).read_text(encoding="utf-8")
    assert text.splitlines()[0] == HEADER
    rows = list(csv.DictReader((path / ANNOTATIONS_FILE).open(encoding="utf-8")))
    row = rows[0]
    assert row["image_path"] == "images/000000.png"
    assert row["human_reviewed"] == "1"
    assert row["confidence"] == "0.9512"
    assert row["reasons"] == "low_confidence|insufficient_readings"
    assert (row["crop_width"], row["crop_height"]) == ("30", "10")
    np.testing.assert_array_equal(cv2.imread(str(path / "images" / "000000.png")), image())
    for file in (path / ANNOTATIONS_FILE, path / "images" / "000000.png"):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    for directory in (tmp_path / "own", path, path / "images"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    with pytest.raises(ExportError):
        store.write_samples([], T0)


def test_empty_export_has_header_only(tmp_path: Path) -> None:
    store = FilesystemLegibilityExportStore(tmp_path / "own")
    path = store.write_samples([], T0)
    assert (path / ANNOTATIONS_FILE).read_text(encoding="utf-8") == f"{HEADER}\n"


def test_no_plate_text_in_csv(tmp_path: Path) -> None:
    store = FilesystemLegibilityExportStore(tmp_path / "own")
    path = store.write_samples([sample(), sample(LegibilityLabel.NOT_PLATE)], T0)
    text = (path / ANNOTATIONS_FILE).read_text(encoding="utf-8")
    for plate in PLATES:
        assert plate not in text


def test_delete_older_than(tmp_path: Path) -> None:
    store = FilesystemLegibilityExportStore(tmp_path / "own")
    assert store.delete_older_than(T0) == 0
    old = store.write_samples([sample()], T0)
    new = store.write_samples([sample()], T0 + timedelta(seconds=1))
    reviewed = tmp_path / "own" / "reviewed-20260926T120000Z"
    reviewed.mkdir()
    past = (datetime.now(UTC) - timedelta(days=200)).timestamp()
    os.utime(old, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=180)) == 1
    assert not old.exists() and new.exists() and reviewed.exists()


def _sample_with_quality() -> LegibilitySample:
    """Crea una muestra con calidad."""
    return LegibilitySample(
        image=image(),
        label=LegibilityLabel.LEGIBLE,
        status=ReviewStatus.CONFIRMED,
        human_reviewed=False,
        video_group=1,
        run_id=1,
        track_id=0,
        vehicle_type=VehicleType.CAR,
        confidence=0.9,
        agreement=0.8,
        num_readings=3,
        reasons=(),
        plate_width_px=100,
        plate_height_px=30,
        sharpness=12.5,
        contrast=40.0,
        frame_width=1920,
        frame_height=1080,
    )


def _sample_without_quality() -> LegibilitySample:
    """Crea una muestra sin calidad."""
    return LegibilitySample(
        image=image(),
        label=LegibilityLabel.LEGIBLE,
        status=ReviewStatus.CONFIRMED,
        human_reviewed=False,
        video_group=1,
        run_id=1,
        track_id=1,
        vehicle_type=VehicleType.CAR,
        confidence=0.9,
        agreement=0.8,
        num_readings=3,
        reasons=(),
        plate_width_px=None,
        plate_height_px=None,
        sharpness=None,
        contrast=None,
        frame_width=None,
        frame_height=None,
    )


def _verify_quality_row(row: dict[str, str], expected: dict[str, str]) -> None:
    """Verifica que una fila del CSV tiene los valores esperados para calidad."""
    for key, expected_value in expected.items():
        assert row[key] == expected_value, f"Mismatch in {key}"


def test_quality_columns(tmp_path: Path) -> None:
    """Las columnas de calidad se escriben correctamente en el CSV."""
    store = FilesystemLegibilityExportStore(tmp_path / "own")
    path = store.write_samples([_sample_with_quality(), _sample_without_quality()], T0)
    rows = list(csv.DictReader((path / ANNOTATIONS_FILE).open(encoding="utf-8")))
    assert len(rows) == 2

    # Primera fila con calidad
    _verify_quality_row(
        rows[0],
        {
            "plate_width_px": "100",
            "plate_height_px": "30",
            "sharpness": "12.5000",
            "contrast": "40.0000",
            "frame_width": "1920",
            "frame_height": "1080",
        },
    )

    # Segunda fila sin calidad
    _verify_quality_row(
        rows[1],
        {
            "plate_width_px": "",
            "plate_height_px": "",
            "sharpness": "",
            "contrast": "",
            "frame_width": "",
            "frame_height": "",
        },
    )
