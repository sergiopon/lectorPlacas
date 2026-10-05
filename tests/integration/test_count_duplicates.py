"""Tests de integración de `count_duplicates` en SQLCipher."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, None, None, "h264")
PLATE = ConsolidatedPlate(
    "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


def test_count_duplicates(tmp_path: Path) -> None:
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider())
    run_id = repo.start_run(RunStart("a" * 64, "p", INFO, T0))
    for track in range(3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, PLATE, None, T0))
    repo.mark_duplicates([(2, 1), (3, 1)])
    browser = repo.browser()
    assert browser.count_duplicates([1, 2, 3]) == {1: 2}
    assert browser.count_duplicates([]) == {}
    repo.close()
