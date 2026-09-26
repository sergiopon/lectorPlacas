"""Tests de revisión de la spec 025 (ocultos al implementador).

Cubren un caso borde que la spec no enumera explícitamente: una segunda ejecución de la
purga sobre datos ya purgados no debe borrar nada.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.entities import ConsolidatedPlate, ReviewStatus, Sighting, VehicleType
from tests.fixtures.fakes import (
    START,
    FakeClock,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

PLATE = ConsolidatedPlate("ABC123", 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())
INFO = VideoInfo(10, 10, 0, None, None, "h264")


def seed(repo: InMemoryPlateRepository, crops: InMemoryCropStore, age_days: int, track: int) -> str:
    at = START - timedelta(days=age_days)
    run_id = repo.start_run(RunStart("a" * 64, "p", INFO, at))
    ref = crops.save(np.zeros((2, 2, 3), np.uint8))
    repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, PLATE, ref, at))
    return ref


def test_purge_is_idempotent() -> None:
    """La segunda ejecución de la purga sobre datos ya purgados no borra nada."""
    repo = InMemoryPlateRepository()
    crops = InMemoryCropStore()
    exports = InMemoryExportStore()
    old = seed(repo, crops, 100, 1)
    new = seed(repo, crops, 1, 2)
    use_case = PurgeExpiredData(repo, crops, exports, FakeClock(), RetentionPolicy(30, 90))
    first = use_case.execute()
    assert (first.crops_deleted, first.sightings_deleted) == (1, 1)
    second = use_case.execute()
    assert (
        second.crops_deleted,
        second.sightings_deleted,
        second.runs_deleted,
        second.plates_deleted,
        second.exports_deleted,
    ) == (0, 0, 0, 0, 0)
    assert set(crops.images) == {new}
    assert old not in crops.images
