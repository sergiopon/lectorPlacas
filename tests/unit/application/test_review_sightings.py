from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.ports import (
    AuditEvent,
    ReviewAction,
    ReviewDecision,
    RunStart,
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
from lector_placas.domain.errors import ReviewError
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

UNVERIFIED = ConsolidatedPlate(
    "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


class ScriptedUI:
    def __init__(self, decisions: list[ReviewDecision]) -> None:
        self.decisions = decisions
        self.crops: list[object] = []
        self.closed = False

    def ask(self, record: SightingRecord, crop: np.ndarray | None) -> ReviewDecision:
        self.crops.append(None if crop is None else crop.shape)
        return self.decisions.pop(0)

    def close(self) -> None:
        self.closed = True


def seed(count: int) -> tuple[InMemoryPlateRepository, InMemoryCropStore]:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track in range(count):
        ref = crops.save(np.zeros((3, 9, 3), np.uint8)) if track == 0 else "f" * 32
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, UNVERIFIED, ref, START))
    return repo, crops


def test_applies_decisions_and_stops_on_quit() -> None:
    repo, crops = seed(5)
    ui = ScriptedUI(
        [
            ReviewDecision(ReviewAction.CONFIRM),
            ReviewDecision(ReviewAction.CORRECT, "ABC128"),
            ReviewDecision(ReviewAction.REJECT),
            ReviewDecision(ReviewAction.SKIP),
            ReviewDecision(ReviewAction.QUIT),
        ]
    )
    summary = ReviewSightings(repo, crops, ui, FakeClock()).execute(10)
    assert (summary.confirmed, summary.corrected, summary.rejected, summary.skipped) == (1, 1, 1, 1)
    statuses = [r.status for r in repo.list_sightings(None, 10, 0)]
    assert statuses == [
        ReviewStatus.CONFIRMED,
        ReviewStatus.CORRECTED,
        ReviewStatus.REJECTED,
        ReviewStatus.UNVERIFIED,
        ReviewStatus.UNVERIFIED,
    ]
    assert repo.get_sighting(2).plate_text == "ABC128"
    assert ui.crops[:2] == [(3, 9, 3), None]
    assert ui.closed
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.REVIEW and "ABC" not in detail


def test_invalid_limit() -> None:
    repo, crops = seed(0)
    with pytest.raises(ReviewError):
        ReviewSightings(repo, crops, ScriptedUI([]), FakeClock()).execute(0)


def test_queue_counts_illegible() -> None:
    repo, crops = seed(1)
    ui = ScriptedUI([ReviewDecision(ReviewAction.ILLEGIBLE)])
    summary = ReviewSightings(repo, crops, ui, FakeClock()).execute(10)
    assert summary.illegible == 1
    assert repo.get_sighting(1).status is ReviewStatus.ILLEGIBLE
