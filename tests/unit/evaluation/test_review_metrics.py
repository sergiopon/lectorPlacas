from __future__ import annotations

import pytest

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.review_metrics import compute_review_metrics
from tests.fixtures.fakes import START, InMemoryPlateRepository

CONFIRMED = ConsolidatedPlate("ABC123", 0.9, 0.9, 5, ReviewStatus.CONFIRMED, (), ())
UNVERIFIED = ConsolidatedPlate(
    "XYZ987",
    0.5,
    0.5,
    2,
    ReviewStatus.UNVERIFIED,
    (UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_AGREEMENT),
    (),
)


def test_metrics_from_review_decisions() -> None:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track, plate in enumerate((CONFIRMED,) * 3 + (UNVERIFIED,) * 3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, None, START))
    repo.record_review(1, ReviewStatus.CONFIRMED, None, START)
    repo.record_review(2, ReviewStatus.CORRECTED, "ABC128", START)
    repo.record_review(4, ReviewStatus.CONFIRMED, None, START)
    repo.record_review(5, ReviewStatus.REJECTED, None, START)
    metrics = compute_review_metrics(repo.list_sightings(None, 100, 0))
    assert (metrics.confirmed_total, metrics.confirmed_audited) == (3, 2)
    assert (metrics.confirmed_kept, metrics.confirmed_corrected, metrics.confirmed_rejected) == (
        1,
        1,
        0,
    )
    assert metrics.precision_confirmed == pytest.approx(0.5)
    assert (
        metrics.unverified_total,
        metrics.unverified_confirmed,
        metrics.unverified_corrected,
    ) == (3, 1, 0)
    assert (metrics.unverified_rejected, metrics.unverified_pending) == (1, 1)
    assert metrics.reason_counts == {"low_agreement": 3, "low_confidence": 3}
    assert metrics.reviewed_readings == 3
    assert metrics.cer == pytest.approx(1 / 18)
    assert metrics.exact_match_rate == pytest.approx(2 / 3)


def test_no_reviews_gives_none_and_empty_raises() -> None:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    repo.save_sighting(Sighting(run_id, 0, 0, 1, VehicleType.CAR, CONFIRMED, None, START))
    metrics = compute_review_metrics(repo.list_sightings(None, 100, 0))
    assert (metrics.precision_confirmed, metrics.cer, metrics.exact_match_rate) == (
        None,
        None,
        None,
    )
    with pytest.raises(EvaluationError):
        compute_review_metrics([])
