"""Tests de revisión de la spec 023 (ocultos al implementador).

Cubren un caso borde que la spec no enumera explícitamente: un track observado pero sin
lecturas, finalizado por inactividad, se reabre como un track nuevo si el mismo
`track_id` reaparece.
"""

from __future__ import annotations

from lector_placas.application.track_registry import TrackRegistry
from lector_placas.domain.entities import BoundingBox, TrackedVehicle, VehicleType

BOX = BoundingBox(0, 0, 10, 10)


def tv(track_id: int, kind: VehicleType = VehicleType.CAR) -> TrackedVehicle:
    return TrackedVehicle(track_id, BOX, 0.9, kind)


def test_track_without_readings_reopened_after_inactivity() -> None:
    """Un track sin lecturas finalizado por inactividad se reabre como avistamiento nuevo."""
    registry = TrackRegistry(2)
    registry.observe([tv(7)], 0)
    finalized = registry.pop_inactive(now_ms=1000, inactive_after_ms=500)
    assert [t.track_id for t in finalized] == [7]
    assert finalized[0].readings == ()
    assert finalized[0].best_crop is None
    assert not registry.needs_reading(7)
    registry.observe([tv(7)], 5000)
    reopened = registry.pop_all()
    assert [t.track_id for t in reopened] == [7]
    assert reopened[0].first_seen_ms == 5000
