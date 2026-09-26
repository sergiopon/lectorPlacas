from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.track_registry import TrackRegistry
from lector_placas.domain.entities import BoundingBox, PlateReading, TrackedVehicle, VehicleType
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError

BOX = BoundingBox(0, 0, 10, 10)


def tv(track_id: int, kind: VehicleType = VehicleType.CAR, conf: float = 0.9) -> TrackedVehicle:
    return TrackedVehicle(track_id, BOX, conf, kind)


def reading(track_id: int, conf: float, quality: float, ts: int = 0) -> PlateReading:
    return PlateReading(track_id, 0, ts, "ABC123", (conf,) * 6, BOX, 0.9, quality)


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
    assert not registry.needs_reading(1)
    with pytest.raises(InvalidEntityError):
        registry.add_reading(reading(1, 0.9, 99.0), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [0, 100]
    assert finalized.best_crop is not None and int(finalized.best_crop[0, 0, 0]) == 2


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
