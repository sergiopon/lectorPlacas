from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fast_plate_ocr.core.types import PlatePrediction

from lector_placas.adapters.inference.plate_reader_fpo import (
    FastPlateOcrReader,
    create_fast_plate_ocr_reader,
)
from lector_placas.domain.entities import OcrResult
from lector_placas.domain.errors import InferenceError, ModelLoadError

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "models" / "fpo-cct-xs-v2-global" / "cct_xs_v2_global.onnx"
CONFIG = ROOT / "models" / "fpo-cct-xs-v2-global-config" / "cct_xs_v2_global_plate_config.yaml"
PROBS = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.99, 0.99, 0.99, 0.99], dtype=np.float32)


class FakeRecognizer:
    def __init__(self, plates: list[str], mode: str = "rgb") -> None:
        self.config = SimpleNamespace(image_color_mode=mode)
        self.plates = plates
        self.received: list[np.ndarray] = []

    def run(
        self, source: list[np.ndarray], return_confidence: bool = False
    ) -> list[PlatePrediction]:
        assert return_confidence
        self.received = source
        return [PlatePrediction(p, PROBS) for p in self.plates]


def blue(n: int = 1) -> list[np.ndarray]:
    image = np.zeros((20, 60, 3), np.uint8)
    image[..., 0] = 255
    return [image] * n


def test_trims_probabilities_and_converts_to_rgb() -> None:
    fake = FakeRecognizer(["ABC123"])
    result = FastPlateOcrReader(fake).read(blue())
    assert result[0].text == "ABC123"
    assert result[0].char_confidences == pytest.approx((0.9, 0.8, 0.7, 0.6, 0.5, 0.4))
    assert fake.received[0][0, 0].tolist() == [0, 0, 255]


def test_grayscale_mode() -> None:
    fake = FakeRecognizer(["AB1"], mode="grayscale")
    FastPlateOcrReader(fake).read(blue())
    assert fake.received[0].ndim == 2


@pytest.mark.parametrize("plate", ["AB_12", "abc123", "ÑBC123"])
def test_invalid_predictions_become_empty(plate: str) -> None:
    fake = FakeRecognizer([plate])
    assert FastPlateOcrReader(fake).read(blue()) == [OcrResult("", ())]


def test_empty_input_and_count_mismatch() -> None:
    assert FastPlateOcrReader(FakeRecognizer([])).read([]) == []
    with pytest.raises(InferenceError):
        FastPlateOcrReader(FakeRecognizer(["A", "B"])).read(blue(1))


def test_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError):
        create_fast_plate_ocr_reader(
            tmp_path / "m.onnx", tmp_path / "c.yaml", ["CPUExecutionProvider"]
        )


@pytest.mark.integration
@pytest.mark.skipif(not (MODEL.exists() and CONFIG.exists()), reason="modelo no descargado")
def test_real_model_reads_synthetic_image() -> None:
    reader = create_fast_plate_ocr_reader(MODEL, CONFIG, ["CPUExecutionProvider"])
    result = reader.read(blue())
    assert len(result) == 1
    assert len(result[0].text) == len(result[0].char_confidences)
