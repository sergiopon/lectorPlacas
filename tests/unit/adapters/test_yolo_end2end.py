from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.inference.letterbox import letterbox
from lector_placas.adapters.inference.onnx_session import create_session
from lector_placas.adapters.inference.yolo_end2end import (
    RawDetection,
    YoloEnd2EndOnnxModel,
    decode_end2end,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError
from tests.fixtures.synthetic_onnx import constant_output_model

ROWS = np.array(
    [
        [
            [0, 16, 64, 48, 0.9, 2],
            [10, 20, 20, 30, 0.1, 3],
            [0, 0, 64, 10, 0.8, 7],
            [0, 16, 32, 48, 0.95, 3],
        ]
    ],
    dtype=np.float32,
)


def transform():  # type: ignore[no-untyped-def]
    return letterbox(np.zeros((100, 200, 3), dtype=np.uint8), 64)[1]


def test_decode_filters_and_sorts() -> None:
    result = decode_end2end(ROWS, transform(), 0.25)
    assert result == [
        RawDetection(BoundingBox(0.0, 0.0, 100.0, 100.0), pytest.approx(0.95), 3),  # type: ignore[arg-type]
        RawDetection(BoundingBox(0.0, 0.0, 200.0, 100.0), pytest.approx(0.9), 2),  # type: ignore[arg-type]
    ]


def test_decode_rejects_bad_shape() -> None:
    with pytest.raises(InferenceError):
        decode_end2end(np.zeros((1, 3, 5), dtype=np.float32), transform(), 0.25)


def test_decode_empty() -> None:
    assert decode_end2end(np.zeros((1, 0, 6), dtype=np.float32), transform(), 0.25) == []


@pytest.mark.integration
def test_predict_with_synthetic_model(tmp_path: Path) -> None:
    session = create_session(constant_output_model(tmp_path / "m.onnx", ROWS), "cpu")
    model = YoloEnd2EndOnnxModel(session, 64)
    detections = model.predict(np.zeros((100, 200, 3), dtype=np.uint8), 0.5)
    assert [d.class_id for d in detections] == [3, 2]


def test_invalid_input_size() -> None:
    class Dummy:
        def run(self, output_names, input_feed):  # type: ignore[no-untyped-def]
            return []

    with pytest.raises(InferenceError):
        YoloEnd2EndOnnxModel(Dummy(), 100)
