from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.vehicle_detector_yolo import YoloVehicleDetector
from lector_placas.adapters.inference.yolo_end2end import RawDetection
from lector_placas.domain.entities import BoundingBox, VehicleType
from lector_placas.domain.errors import InferenceError

BOX = BoundingBox(1, 1, 10, 10)


class FakeModel:
    def __init__(self, rows: list[RawDetection]) -> None:
        self.rows = rows
        self.thresholds: list[float] = []

    def predict(self, image: np.ndarray, score_threshold: float) -> list[RawDetection]:
        self.thresholds.append(score_threshold)
        return self.rows


def test_maps_coco_classes_and_drops_others() -> None:
    model = FakeModel(
        [
            RawDetection(BOX, 0.9, 2),
            RawDetection(BOX, 0.8, 0),
            RawDetection(BOX, 0.7, 3),
            RawDetection(BOX, 0.6, 5),
            RawDetection(BOX, 0.5, 7),
            RawDetection(BOX, 0.4, 1),
        ]
    )
    detections = YoloVehicleDetector(model, 0.25).detect(np.zeros((10, 10, 3), np.uint8))
    assert [d.vehicle_type for d in detections] == [
        VehicleType.CAR,
        VehicleType.MOTORCYCLE,
        VehicleType.BUS,
        VehicleType.TRUCK,
    ]
    assert [d.confidence for d in detections] == [0.9, 0.7, 0.6, 0.5]
    assert model.thresholds == [0.25]


def test_invalid_threshold() -> None:
    with pytest.raises(InferenceError):
        YoloVehicleDetector(FakeModel([]), 1.5)
