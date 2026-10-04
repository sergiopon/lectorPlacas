"""Tests de integración del marcado de duplicados en SQLCipher (spec 061)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import RunStart, SightingQuery, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import RepositoryError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, None, None, "h264")
PLATE = ConsolidatedPlate(
    "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


def seed(tmp_path: Path) -> SqlCipherPlateRepository:
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider())
    run_id = repo.start_run(RunStart("a" * 64, "p", INFO, T0))
    for track in range(3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, PLATE, None, T0))
    return repo


def test_mark_and_read_back(tmp_path: Path) -> None:
    repo = seed(tmp_path)
    repo.mark_duplicates([(2, 1), (3, 1)])
    assert repo.get_sighting(2).duplicate_of == 1
    assert repo.get_sighting(3).duplicate_of == 1
    assert repo.get_sighting(1).duplicate_of is None
    repo.mark_duplicates([])
    repo.close()


def test_browser_filter(tmp_path: Path) -> None:
    repo = seed(tmp_path)
    repo.mark_duplicates([(2, 1), (3, 1)])
    browser = repo.browser()
    found = browser.search_sightings(SightingQuery(), 10, 0)
    assert [r.sighting_id for r in found] == [1]
    assert browser.count_sightings(SightingQuery()) == 1
    query = SightingQuery(include_duplicates=True)
    assert len(browser.search_sightings(query, 10, 0)) == 3
    assert browser.count_sightings(query) == 3
    repo.close()


def test_invalid_target_rolls_back(tmp_path: Path) -> None:
    repo = seed(tmp_path)
    with pytest.raises(RepositoryError):
        repo.mark_duplicates([(2, 1), (3, 999)])
    assert repo.get_sighting(2).duplicate_of is None
    repo.close()
