"""Tests de las métricas ocultas en review_metrics (spec 064)."""

from __future__ import annotations

from datetime import UTC, datetime

from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
from lector_placas.evaluation.review_metrics import compute_review_metrics
from tests.fixtures.fakes import fake_sighting_record


def test_hidden_counts() -> None:
    """Calcula hidden_* correctamente con avistamientos ocultos."""
    now = datetime.now(UTC)
    repo_c = fake_sighting_record(
        sighting_id=3,
        status=ReviewStatus.CORRECTED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
        reviewed_at=now,
    )
    repo_d = fake_sighting_record(
        sighting_id=4,
        status=ReviewStatus.REJECTED,
        reasons=(UnverifiedReason.PREDICTED_NOT_PLATE,),
        reviewed_at=now,
    )
    repo_e = fake_sighting_record(
        sighting_id=5,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
        reviewed_at=None,
    )
    metrics = compute_review_metrics([repo_c, repo_d, repo_e])
    assert metrics.hidden_total == 3
    assert metrics.hidden_legible == 1
    assert metrics.hidden_unusable == 1
    assert metrics.hidden_pending == 1


def test_no_hidden() -> None:
    """Sin avistamientos ocultos, todos los hidden_* son 0."""
    a = fake_sighting_record(
        sighting_id=1,
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    metrics = compute_review_metrics([a, b])
    assert metrics.hidden_total == 0
    assert metrics.hidden_legible == 0
    assert metrics.hidden_unusable == 0
    assert metrics.hidden_pending == 0
