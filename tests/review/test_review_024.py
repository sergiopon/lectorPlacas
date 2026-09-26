from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.domain.entities import (
    BoundingBox,
    PlateDetection,
    TrackedVehicle,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import ConsolidationError
from tests.unit.application.test_process_video import (
    SHA,
    CyclingReader,
    FixedPlateDetector,
    build,
)


class TwoTrackTracker:
    def update(self, detections, image, timestamp_ms):  # type: ignore[no-untyped-def]
        big = BoundingBox(100, 100, 400, 300)
        small = BoundingBox(450, 100, 550, 200)
        return [
            TrackedVehicle(1, small, 0.9, VehicleType.CAR),
            TrackedVehicle(2, big, 0.9, VehicleType.CAR),
        ]

    def reset(self) -> None:
        return None


class ShapeRecorder(FixedPlateDetector):
    pass


def test_max_ocr_per_frame_reads_largest_vehicle_first() -> None:
    process, _parts = build([0])
    plates = ShapeRecorder()
    process._deps = type(process._deps)(  # type: ignore[misc]
        **{
            **{f: getattr(process._deps, f) for f in process._deps.__slots__},
            "tracker": TwoTrackTracker(),
            "plate_detector": plates,
        }
    )
    process._settings = type(process._settings)(  # type: ignore[misc]
        **{
            **{f: getattr(process._settings, f) for f in process._settings.__slots__},
            "max_ocr_per_frame": 1,
        }
    )
    process.execute(Path("v.mp4"), SHA)
    assert len(plates.shapes) == 1
    assert plates.shapes[0] == (240, 360, 3)


class FailingConsolidator:
    def consolidate(self, readings, vehicle_type):  # type: ignore[no-untyped-def]
        raise ConsolidationError("sintético")


def test_consolidation_error_marks_run_failed() -> None:
    process, parts = build([0, 100, 200])
    process._deps = type(process._deps)(  # type: ignore[misc]
        **{
            **{f: getattr(process._deps, f) for f in process._deps.__slots__},
            "consolidator": FailingConsolidator(),
        }
    )
    with pytest.raises(ConsolidationError):
        process.execute(Path("v.mp4"), SHA)
    assert parts["repo"].runs[1].succeeded is False
    assert parts["source"].closed


class OutsidePlateDetector:
    def detect(self, image):  # type: ignore[no-untyped-def]
        return [PlateDetection(BoundingBox(600, 450, 700, 500), 0.9)]


def test_plate_outside_frame_is_discarded() -> None:
    process, parts = build([0, 100, 200], reader=CyclingReader(["ABC123"]))
    process._deps = type(process._deps)(  # type: ignore[misc]
        **{
            **{f: getattr(process._deps, f) for f in process._deps.__slots__},
            "plate_detector": OutsidePlateDetector(),
        }
    )
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert stats.tracks_without_reading == 1
    assert parts["reader"].calls == 0


def test_vehicle_detection_unused_import_guard() -> None:
    assert VehicleDetection(BoundingBox(0, 0, 1, 1), 0.5, VehicleType.BUS).confidence == 0.5
