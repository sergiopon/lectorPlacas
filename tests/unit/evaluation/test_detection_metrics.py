from __future__ import annotations

import pytest

from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.detection_metrics import DetectionCounts, iou, match_image, summarize

A = BoundingBox(0, 0, 10, 10)


def test_iou() -> None:
    assert iou(A, A) == pytest.approx(1.0)
    assert iou(A, BoundingBox(5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert iou(A, BoundingBox(20, 20, 30, 30)) == 0.0


def test_match_is_greedy_by_confidence() -> None:
    low = PlateDetection(BoundingBox(1, 0, 11, 10), 0.4)
    high = PlateDetection(BoundingBox(0, 0, 10, 10), 0.9)
    assert match_image([low, high], [A]) == DetectionCounts(1, 1, 0)


def test_match_counts_misses_and_threshold() -> None:
    far = PlateDetection(BoundingBox(5, 0, 15, 10), 0.8)
    assert match_image([far], [A, BoundingBox(50, 50, 60, 60)]) == DetectionCounts(0, 1, 2)
    assert match_image([far], [A], threshold=0.3) == DetectionCounts(1, 0, 0)
    assert match_image([], []) == DetectionCounts(0, 0, 0)


def test_summarize() -> None:
    metrics = summarize(
        [DetectionCounts(3, 1, 0), DetectionCounts(1, 0, 2), DetectionCounts(0, 0, 0)]
    )
    assert metrics.images == 3
    assert metrics.precision == pytest.approx(0.8)
    assert metrics.recall == pytest.approx(4 / 6)
    assert metrics.f1 == pytest.approx(2 * 0.8 * (4 / 6) / (0.8 + 4 / 6))
    empty = summarize([DetectionCounts(0, 0, 0)])
    assert (empty.precision, empty.recall, empty.f1) == (None, None, None)
    with pytest.raises(EvaluationError):
        summarize([])
