from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.track_registry import TrackRegistry
from lector_placas.domain.entities import BoundingBox, PlateReading, TrackedVehicle, VehicleType
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError

BOX = BoundingBox(0, 0, 10, 10)


def tv(track_id: int, kind: VehicleType = VehicleType.CAR, conf: float = 0.9) -> TrackedVehicle:
    return TrackedVehicle(track_id, BOX, conf, kind)


def reading(
    track_id: int, conf: float, quality: float, ts: int = 0, width: float = 10
) -> PlateReading:
    box = BoundingBox(0, 0, width, 10)
    return PlateReading(track_id, 0, ts, "ABC123", (conf,) * 6, box, 0.9, quality)


def crop(value: int) -> np.ndarray:
    return np.full((2, 2, 3), value, np.uint8)


def test_lifecycle_and_ordering() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(5), tv(3)], 0)
    registry.observe([tv(5)], 500)
    assert registry.active_count == 2
    inactive = registry.pop_inactive(now_ms=1200, inactive_after_ms=1000)
    assert [t.track_id for t in inactive] == [3]
    assert (inactive[0].first_seen_ms, inactive[0].last_seen_ms) == (0, 0)
    remaining = registry.pop_all()
    assert [(t.track_id, t.first_seen_ms, t.last_seen_ms) for t in remaining] == [(5, 0, 500)]
    assert registry.active_count == 0


def test_reading_limit_and_best_crop() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    assert registry.needs_reading(1)
    registry.add_reading(reading(1, 0.5, 10.0), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100), crop(2))
    assert registry.needs_reading(1)
    assert registry.is_full(1)
    registry.add_reading(reading(1, 0.9, 5.0, ts=200), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [0, 100]
    assert finalized.best_crop is not None and int(finalized.best_crop[0, 0, 0]) == 2


def test_wider_plate_replaces_worst_reading() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    registry.add_reading(reading(1, 0.9, 10.0, ts=0, width=20), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100, width=40), crop(2))
    registry.add_reading(reading(1, 0.9, 10.0, ts=200, width=60), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [100, 200]


def test_sharpness_breaks_width_tie() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    registry.add_reading(reading(1, 0.9, 5.0, ts=0), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100), crop(2))
    registry.add_reading(reading(1, 0.9, 7.0, ts=200), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [100, 200]


def test_equal_quality_keeps_earliest_readings() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    registry.add_reading(reading(1, 0.9, 10.0, ts=0), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100), crop(2))
    registry.add_reading(reading(1, 0.9, 10.0, ts=200), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [0, 100]


def test_readings_are_returned_in_time_order() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    registry.add_reading(reading(1, 0.9, 10.0, ts=300, width=30), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100, width=20), crop(2))
    registry.add_reading(reading(1, 0.9, 10.0, ts=200, width=40), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [200, 300]


def test_best_crop_can_come_from_discarded_reading() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1)], 0)
    registry.add_reading(reading(1, 0.5, 1.0, ts=0, width=40), crop(1))
    registry.add_reading(reading(1, 0.9, 50.0, ts=100, width=20), crop(2))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [0]
    assert finalized.best_crop is not None and int(finalized.best_crop[0, 0, 0]) == 2


def test_is_full_for_unknown_and_partial_tracks() -> None:
    registry = TrackRegistry(2)
    assert not registry.is_full(9)
    registry.observe([tv(1)], 0)
    assert not registry.is_full(1)
    registry.add_reading(reading(1, 0.9, 10.0), crop(1))
    assert not registry.is_full(1)
    registry.add_reading(reading(1, 0.9, 10.0, ts=100), crop(2))
    assert registry.is_full(1)


def test_unknown_track_and_needs_reading() -> None:
    registry = TrackRegistry(1)
    assert not registry.needs_reading(9)
    with pytest.raises(InvalidEntityError):
        registry.add_reading(reading(9, 0.9, 1.0), crop(1))


def test_vehicle_type_majority_and_ties() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1, VehicleType.TRUCK, 0.9)], 0)
    registry.observe([tv(1, VehicleType.BUS, 0.6)], 100)
    registry.observe([tv(1, VehicleType.BUS, 0.6)], 200)
    registry.observe([tv(2, VehicleType.TRUCK, 0.5)], 0)
    registry.observe([tv(2, VehicleType.CAR, 0.5)], 100)
    types = {t.track_id: t.vehicle_type for t in registry.pop_all()}
    assert types == {1: VehicleType.BUS, 2: VehicleType.CAR}


def test_track_without_readings_has_no_crop() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1)], 0)
    finalized = registry.pop_all()[0]
    assert finalized.readings == () and finalized.best_crop is None


def test_reappearing_id_is_new_track() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1)], 0)
    registry.pop_all()
    registry.observe([tv(1)], 5000)
    assert registry.pop_all()[0].first_seen_ms == 5000


def test_invalid_limit() -> None:
    with pytest.raises(ConfigurationError):
        TrackRegistry(0)
