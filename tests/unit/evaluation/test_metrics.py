from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.evaluation.ground_truth import GroundTruth, GroundTruthPlate
from lector_placas.evaluation.metrics import compute_metrics, overlaps

T0 = datetime(2026, 9, 24, tzinfo=UTC)
C, U, R, K = (
    ReviewStatus.CONFIRMED,
    ReviewStatus.UNVERIFIED,
    ReviewStatus.REJECTED,
    ReviewStatus.CORRECTED,
)


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


def gt(text: str, first: int, last: int, legible: bool = True) -> GroundTruthPlate:
    return GroundTruthPlate(
        text=text,
        vehicle_type=VehicleType.CAR,
        first_seen_ms=first,
        last_seen_ms=last,
        legible=legible,
    )


TRUTH = GroundTruth(
    version=1,
    video_sha256="a" * 64,
    subset="street_day",
    camera="fixed",
    plates=(
        gt("ABC123", 1000, 3000),
        gt("XYZ98K", 5000, 6000),
        gt("DEF456", 8000, 9000),
        gt("", 10000, 11000, legible=False),
    ),
)


def test_compute_metrics() -> None:
    records = [
        rec(1, "ABC123", 1200, 2800, C),
        rec(2, "XYZ98L", 5100, 5900, C),
        rec(3, "DEF456", 8100, 8900, U),
        rec(4, "ABC123", 20000, 21000, C),
        rec(5, "XYZ98K", 5000, 6000, R),
        rec(6, "XYZ98K", 5200, 5800, K),
    ]
    metrics = compute_metrics(records, TRUTH)
    assert (metrics.gt_legible, metrics.confirmed_total, metrics.confirmed_matched) == (3, 3, 1)
    assert (metrics.any_matched, metrics.corrected_total) == (3, 1)
    assert metrics.precision_confirmed == pytest.approx(1 / 3)
    assert metrics.recall_any == pytest.approx(1.0)
    assert metrics.recall_confirmed == pytest.approx(1 / 3)


def test_one_to_one_matching() -> None:
    records = [rec(1, "ABC123", 1000, 2000, C), rec(2, "ABC123", 1500, 2500, C)]
    assert compute_metrics(records, TRUTH).confirmed_matched == 1


def test_overlap_tolerance() -> None:
    plate = gt("XYZ98K", 5000, 6000)
    assert overlaps(rec(1, "XYZ98K", 4100, 4500, U), plate, 1000)
    assert not overlaps(rec(1, "XYZ98K", 3500, 3900, U), plate, 1000)


def test_empty_denominators() -> None:
    metrics = compute_metrics(
        [],
        GroundTruth(version=1, video_sha256="a" * 64, subset="fast", camera="handheld", plates=()),
    )
    assert metrics.precision_confirmed is None and metrics.recall_any is None
