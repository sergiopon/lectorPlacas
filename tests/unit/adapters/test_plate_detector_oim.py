from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from open_image_models.detection.core.base import BoundingBox as OimBox
from open_image_models.detection.core.base import DetectionResult

from lector_placas.adapters.inference.plate_detector_oim import (
    OimPlateDetector,
    create_oim_plate_detector,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import ModelLoadError

ROOT = Path(__file__).resolve().parents[3]
REAL_MODEL = (
    ROOT / "models" / "oim-yolo-v9-t-384-plates" / "yolo-v9-t-384-license-plates-end2end.onnx"
)


class FakeOim:
    def __init__(self, results: list[DetectionResult]) -> None:
        self.results = results

    def predict(self, images: np.ndarray) -> list[DetectionResult]:
        return self.results


def result(conf: float, x1: int, y1: int, x2: int, y2: int) -> DetectionResult:
    return DetectionResult("License Plate", conf, OimBox(x1, y1, x2, y2))


def test_converts_clips_and_sorts() -> None:
    fake = FakeOim(
        [result(0.5, 10, 10, 50, 30), result(0.9, -5, 2, 300, 20), result(0.7, 60, 60, 60, 70)]
    )
    detections = OimPlateDetector(fake).detect(np.zeros((40, 100, 3), np.uint8))
    assert [d.confidence for d in detections] == [0.9, 0.5]
    assert detections[0].box == BoundingBox(0.0, 2.0, 100.0, 20.0)
    assert detections[1].box == BoundingBox(10.0, 10.0, 50.0, 30.0)


def test_small_images_return_empty() -> None:
    fake = FakeOim([result(0.9, 0, 0, 5, 5)])
    assert OimPlateDetector(fake).detect(np.zeros((10, 100, 3), np.uint8)) == []


def test_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError):
        create_oim_plate_detector(tmp_path / "no.onnx", 0.25, ["CPUExecutionProvider"])


@pytest.mark.integration
@pytest.mark.skipif(not REAL_MODEL.exists(), reason="modelo no descargado (lector models fetch)")
def test_real_model_runs_on_blank_image() -> None:
    detector = create_oim_plate_detector(REAL_MODEL, 0.25, ["CPUExecutionProvider"])
    assert isinstance(detector.detect(np.zeros((200, 300, 3), np.uint8)), list)
