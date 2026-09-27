from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.ports import ReviewAction, ReviewDecision, RunStart, VideoInfo
from lector_placas.application.review_sightings import ReviewSightings
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ReviewError
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

CONFIRMED = ConsolidatedPlate("ABC123", 0.9, 0.9, 5, ReviewStatus.CONFIRMED, (), ())
UNVERIFIED = ConsolidatedPlate(
    "XYZ987", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


class ScriptedUI:
    def __init__(self, decisions: list[ReviewDecision]) -> None:
        self.decisions = decisions
        self.seen: list[int] = []

    def ask(self, record: SightingRecord, crop: np.ndarray | None) -> ReviewDecision:
        self.seen.append(record.sighting_id)
        return self.decisions.pop(0)

    def close(self) -> None:
        pass


def seed() -> InMemoryPlateRepository:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track, plate in enumerate((CONFIRMED, UNVERIFIED, CONFIRMED, CONFIRMED)):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, None, START))
    return repo


def test_audits_only_unreviewed_confirmed() -> None:
    repo = seed()
    repo.record_review(1, ReviewStatus.CONFIRMED, None, START)
    ui = ScriptedUI(
        [ReviewDecision(ReviewAction.CORRECT, "ABC128"), ReviewDecision(ReviewAction.CONFIRM)]
    )
    summary = ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(
        5, ReviewStatus.CONFIRMED
    )
    assert ui.seen == [3, 4]
    assert (summary.confirmed, summary.corrected) == (1, 1)
    assert repo.get_sighting(3).status is ReviewStatus.CORRECTED
    assert repo.get_sighting(4).reviewed_at is not None


def test_default_status_is_unverified_and_rejects_others() -> None:
    repo = seed()
    ui = ScriptedUI([ReviewDecision(ReviewAction.SKIP)])
    ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(5)
    assert ui.seen == [2]
    with pytest.raises(ReviewError):
        ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(
            5, ReviewStatus.REJECTED
        )
