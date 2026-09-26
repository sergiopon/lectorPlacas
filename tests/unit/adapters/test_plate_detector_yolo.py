from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.plate_detector_yolo import YoloPlateDetector
from lector_placas.adapters.inference.yolo_end2end import RawDetection
from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import InferenceError

BOX = BoundingBox(1, 1, 10, 5)


class FakeModel:
    def predict(self, image: np.ndarray, score_threshold: float) -> list[RawDetection]:
        return [RawDetection(BOX, 0.9, 0), RawDetection(BOX, 0.8, 1), RawDetection(BOX, 0.3, 0)]


def test_keeps_plate_class_only() -> None:
    detections = YoloPlateDetector(FakeModel(), 0.25).detect(np.zeros((32, 32, 3), np.uint8))
    assert detections == [PlateDetection(BOX, 0.9), PlateDetection(BOX, 0.3)]


def test_small_image() -> None:
    assert YoloPlateDetector(FakeModel(), 0.25).detect(np.zeros((8, 32, 3), np.uint8)) == []


def test_invalid_threshold() -> None:
    with pytest.raises(InferenceError):
        YoloPlateDetector(FakeModel(), -0.1)
