"""Tests de aceptación de la parada temprana en `TrackRegistry` (spec 060)."""

from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.track_registry import TrackRegistry
from lector_placas.domain.entities import (
    BoundingBox,
    PlateReading,
    TrackedVehicle,
    VehicleType,
)
from lector_placas.domain.errors import InvalidEntityError

BOX = BoundingBox(10, 10, 100, 100)
PLATE_BOX = BoundingBox(0, 0, 50, 20)


def _vehicle(track_id: int, vehicle_type: VehicleType = VehicleType.CAR) -> TrackedVehicle:
    return TrackedVehicle(track_id, BOX, 0.9, vehicle_type)


def _reading(track_id: int, timestamp_ms: int) -> PlateReading:
    return PlateReading(
        track_id, timestamp_ms // 100, timestamp_ms, "ABC123", (0.9,) * 6, PLATE_BOX, 0.9, 50.0
    )


def _crop() -> np.ndarray:
    return np.zeros((10, 20, 3), dtype=np.uint8)


def test_mark_resolved_stops_needs_reading() -> None:
    registry = TrackRegistry(3)
    registry.observe([_vehicle(1), _vehicle(2)], 0)
    registry.mark_resolved(1)
    assert registry.needs_reading(1) is False
    assert registry.needs_reading(2) is True


def test_resolved_track_is_still_observed_and_finalized() -> None:
    registry = TrackRegistry(3)
    registry.observe([_vehicle(1)], 0)
    registry.add_reading(_reading(1, 0), _crop())
    registry.mark_resolved(1)
    registry.observe([_vehicle(1)], 500)
    finalized = registry.pop_all()
    assert len(finalized) == 1
    assert finalized[0].last_seen_ms == 500
    assert len(finalized[0].readings) == 1


def test_readings_are_sorted() -> None:
    registry = TrackRegistry(5)
    registry.observe([_vehicle(1)], 0)
    for timestamp_ms in (300, 100, 200):
        registry.add_reading(_reading(1, timestamp_ms), _crop())
    assert [r.timestamp_ms for r in registry.readings(1)] == [100, 200, 300]


def test_vehicle_type_is_dominant() -> None:
    registry = TrackRegistry(3)
    registry.observe([_vehicle(1, VehicleType.CAR)], 0)
    registry.observe([_vehicle(1, VehicleType.CAR)], 100)
    registry.observe([_vehicle(1, VehicleType.MOTORCYCLE)], 200)
    assert registry.vehicle_type(1) is VehicleType.CAR


def test_unknown_track_raises() -> None:
    registry = TrackRegistry(3)
    with pytest.raises(InvalidEntityError):
        registry.readings(99)
    with pytest.raises(InvalidEntityError):
        registry.vehicle_type(99)
    with pytest.raises(InvalidEntityError):
        registry.mark_resolved(99)
