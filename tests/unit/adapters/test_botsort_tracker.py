from __future__ import annotations

import numpy as np

from lector_placas.adapters.tracking.botsort_tracker import (
    BotSortTracker,
    TrackerSettings,
    from_supervision,
    to_supervision,
)
from lector_placas.domain.entities import BoundingBox, VehicleDetection, VehicleType

SETTINGS = TrackerSettings(30, 10.0, 0.7, 2, 0.2, 0.5, 0.3, 0.6, "sparseOptFlow", 2)
BACKGROUND = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)


def det(x: float, y: float, kind: VehicleType = VehicleType.CAR) -> VehicleDetection:
    return VehicleDetection(BoundingBox(x, y, x + 60, y + 40), 0.9, kind)


def test_conversion_roundtrip() -> None:
    sv_dets = to_supervision([det(10, 20, VehicleType.BUS)])
    sv_dets.tracker_id = np.array([4])
    tracked = from_supervision(sv_dets)
    assert tracked[0].track_id == 4
    assert tracked[0].vehicle_type is VehicleType.BUS
    assert tracked[0].box == BoundingBox(10.0, 20.0, 70.0, 60.0)


def test_empty_conversion() -> None:
    assert len(to_supervision([])) == 0


def test_moving_vehicle_keeps_id() -> None:
    tracker = BotSortTracker(SETTINGS)
    ids = []
    for step in range(6):
        result = tracker.update([det(20 + 5 * step, 50)], BACKGROUND, step * 100)
        ids.extend(t.track_id for t in result)
    assert ids and len(set(ids)) == 1
    assert ids[0] >= 0


def test_two_vehicles_get_distinct_ids_and_reset_restarts() -> None:
    tracker = BotSortTracker(SETTINGS)
    first = tracker.update([det(10, 10), det(200, 150, VehicleType.MOTORCYCLE)], BACKGROUND, 0)
    assert len({t.track_id for t in first}) == 2
    assert {t.vehicle_type for t in first} == {VehicleType.CAR, VehicleType.MOTORCYCLE}
    tracker.reset()
    again = tracker.update([det(10, 10)], BACKGROUND, 0)
    assert [t.track_id for t in again] == [0]


def test_empty_frame_is_accepted() -> None:
    tracker = BotSortTracker(SETTINGS)
    tracker.update([det(10, 10)], BACKGROUND, 0)
    assert tracker.update([], BACKGROUND, 100) == []
