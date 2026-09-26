from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.letterbox import (
    PAD_VALUE,
    box_to_source,
    letterbox,
    to_model_input,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError


def test_letterbox_wide_image() -> None:
    image = np.full((100, 200, 3), 50, dtype=np.uint8)
    canvas, t = letterbox(image, 64)
    assert canvas.shape == (64, 64, 3)
    assert (t.scale, t.pad_x, t.pad_y, t.source_width, t.source_height) == (0.32, 0, 16, 200, 100)
    assert (canvas[:16] == PAD_VALUE).all()
    assert (canvas[16:48] == 50).all()
    assert (canvas[48:] == PAD_VALUE).all()


def test_box_roundtrip_and_clipping() -> None:
    _, t = letterbox(np.zeros((100, 200, 3), dtype=np.uint8), 64)
    assert box_to_source(0, 16, 64, 48, t) == BoundingBox(0.0, 0.0, 200.0, 100.0)
    assert box_to_source(0, 0, 64, 10, t) is None
    assert box_to_source(-10, 16, 32, 48, t) == BoundingBox(0.0, 0.0, 100.0, 100.0)


def test_to_model_input_rgb_chw() -> None:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[..., 0] = 255  # azul en BGR
    tensor = to_model_input(image)
    assert tensor.shape == (1, 3, 4, 4)
    assert tensor.dtype == np.float32
    assert tensor.flags["C_CONTIGUOUS"]
    assert tensor[0, 2].max() == pytest.approx(1.0)
    assert tensor[0, 0].max() == 0.0


def test_invalid_size() -> None:
    with pytest.raises(InferenceError):
        letterbox(np.zeros((4, 4, 3), dtype=np.uint8), 0)
