from __future__ import annotations

import cv2
import numpy as np
import pytest

from lector_placas.adapters.imaging.quality import LaplacianQualityScorer
from lector_placas.domain.errors import InferenceError


def checkerboard() -> np.ndarray:
    tile = np.kron([[0, 255] * 8, [255, 0] * 8] * 4, np.ones((4, 4))).astype(np.uint8)
    return np.dstack([tile] * 3)


def test_flat_image_is_zero() -> None:
    assert LaplacianQualityScorer().sharpness(np.full((30, 90, 3), 128, np.uint8)) == 0.0


def test_sharp_beats_blurred() -> None:
    sharp = checkerboard()
    blurred = cv2.GaussianBlur(sharp, (9, 9), 3)
    scorer = LaplacianQualityScorer()
    assert scorer.sharpness(sharp) > scorer.sharpness(blurred) > 0.0


def test_empty_image_raises() -> None:
    with pytest.raises(InferenceError):
        LaplacianQualityScorer().sharpness(np.zeros((0, 10, 3), np.uint8))
