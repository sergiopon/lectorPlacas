"""Tests de aceptación: la revisión y el navegador omiten duplicados (spec 061)."""

from __future__ import annotations

import numpy as np

from lector_placas.application.ports import (
    ReviewAction,
    ReviewDecision,
    RunStart,
    SightingQuery,
    VideoInfo,
)
from lector_placas.application.review_sightings import ReviewSightings
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

UNVERIFIED = ConsolidatedPlate(
    "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


class RecordingUI:
    def __init__(self) -> None:
        self.asked: list[int] = []

    def ask(self, record: SightingRecord, crop: np.ndarray | None) -> ReviewDecision:
        self.asked.append(record.sighting_id)
        return ReviewDecision(ReviewAction.SKIP)

    def close(self) -> None:
        pass


def seed() -> InMemoryPlateRepository:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track in range(2):
        repo.save_sighting(
            Sighting(run_id, track, 0, 1, VehicleType.CAR, UNVERIFIED, "f" * 32, START)
        )
    repo.mark_duplicates([(2, 1)])
    return repo


def test_review_skips_duplicates() -> None:
    repo = seed()
    ui = RecordingUI()
    ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(10)
    assert ui.asked == [1]


def test_browser_hides_duplicates_by_default() -> None:
    repo = seed()
    found = repo.search_sightings(SightingQuery(), 10, 0)
    assert [r.sighting_id for r in found] == [1]
    assert repo.count_sightings(SightingQuery()) == 1
    query = SightingQuery(include_duplicates=True)
    assert len(repo.search_sightings(query, 10, 0)) == 2
    assert repo.count_sightings(query) == 2
