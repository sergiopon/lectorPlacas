from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.evaluation.ground_truth import GroundTruth, GroundTruthPlate
from lector_placas.evaluation.metrics import PlateMetrics, compute_metrics

T0 = datetime(2026, 10, 4, tzinfo=UTC)
C, U = ReviewStatus.CONFIRMED, ReviewStatus.UNVERIFIED


def rec(sid: int, text: str, first: int, last: int, status: ReviewStatus) -> SightingRecord:
    return SightingRecord(
        sid,
        1,
        sid,
        first,
        last,
        VehicleType.CAR,
        text,
        text,
        0.9,
        0.9,
        3,
        status,
        (),
        (),
        None,
        T0,
        None,
    )


def gt(text: str, first: int, last: int, width: int | None = None) -> GroundTruthPlate:
    return GroundTruthPlate(
        text=text,
        vehicle_type=VehicleType.CAR,
        first_seen_ms=first,
        last_seen_ms=last,
        legible=True,
        max_plate_width_px=width,
    )


TRUTH_V2 = GroundTruth(
    version=2,
    video_sha256="a" * 64,
    subset="street_day",
    camera="fixed",
    plates=(
        gt("ABC123", 0, 1000, 60),
        gt("DEF456", 2000, 3000, 40),
        gt("GHI789", 4000, 5000, 50),
    ),
)

TRUTH_V1 = GroundTruth(
    version=1,
    video_sha256="a" * 64,
    subset="street_day",
    camera="fixed",
    plates=(
        gt("ABC123", 0, 1000),
        gt("DEF456", 2000, 3000),
        gt("GHI789", 4000, 5000),
    ),
)

RECORDS = [
    rec(1, "ABC123", 0, 900, C),
    rec(2, "DEF456", 2100, 2900, C),
    rec(3, "GHI789", 4100, 4900, U),
]


def test_near_filter() -> None:
    metrics = compute_metrics(RECORDS, TRUTH_V2, min_plate_width=48)
    assert (metrics.gt_legible, metrics.gt_far_excluded) == (2, 1)
    assert (
        metrics.confirmed_matched,
        metrics.confirmed_matched_near,
        metrics.any_matched,
    ) == (2, 1, 2)
    assert metrics.precision_confirmed == pytest.approx(1.0)
    assert metrics.recall_any == pytest.approx(1.0)
    assert metrics.recall_confirmed == pytest.approx(0.5)
    assert metrics.min_plate_width == 48


def test_without_min_width() -> None:
    metrics = compute_metrics(RECORDS, TRUTH_V2, min_plate_width=None)
    assert metrics.gt_legible == 3
    assert metrics.gt_far_excluded == 0
    assert metrics.recall_any == pytest.approx(1.0)
    assert metrics.recall_confirmed == pytest.approx(2 / 3)


def test_v1_ignores_min_width() -> None:
    metrics = compute_metrics(RECORDS, TRUTH_V1, min_plate_width=48)
    assert metrics.gt_legible == 3
    assert metrics.gt_far_excluded == 0
    assert metrics.recall_any == pytest.approx(1.0)
    assert metrics.recall_confirmed == pytest.approx(2 / 3)
    assert metrics.min_plate_width is None


def test_old_constructor_still_works() -> None:
    assert PlateMetrics(3, 2, 2, 3, 0).recall_confirmed == pytest.approx(2 / 3)
