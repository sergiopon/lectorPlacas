from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from lector_placas.application.ports import AuditEvent, RunStart, VideoInfo
from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.entities import ConsolidatedPlate, ReviewStatus, Sighting, VehicleType
from lector_placas.domain.errors import ConfigurationError
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


def test_purges_by_age() -> None:
    repo, crops, exports = InMemoryPlateRepository(), InMemoryCropStore(), InMemoryExportStore(2)
    old = seed(repo, crops, 100, 1)
    mid = seed(repo, crops, 40, 2)
    new = seed(repo, crops, 1, 3)
    result = PurgeExpiredData(repo, crops, exports, FakeClock(), RetentionPolicy(30, 90)).execute()
    assert (result.crops_deleted, result.sightings_deleted, result.runs_deleted) == (2, 1, 1)
    assert result.exports_deleted == 2
    assert set(crops.images) == {new}
    assert old not in crops.images and mid not in crops.images
    assert [r.track_id for r in repo.list_sightings(None, 10, 0)] == [2, 3]
    assert crops.swept_before == [START - timedelta(days=30)]
    assert exports.deleted_before == [START - timedelta(days=90)]
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.PURGE
    assert "ABC123" not in detail and "recortes=2" in detail


def test_nothing_to_purge() -> None:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    seed(repo, crops, 1, 1)
    result = PurgeExpiredData(
        repo, crops, InMemoryExportStore(), FakeClock(), RetentionPolicy(30, 90)
    ).execute()
    assert (result.crops_deleted, result.sightings_deleted, result.exports_deleted) == (0, 0, 0)


@pytest.mark.parametrize("crops_days,records_days", [(0, 90), (91, 90)])
def test_invalid_policy(crops_days: int, records_days: int) -> None:
    with pytest.raises(ConfigurationError):
        RetentionPolicy(crops_days, records_days)
