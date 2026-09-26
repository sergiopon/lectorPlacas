from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.image_ops import crop_image
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InvalidEntityError


def test_crop_floor_ceil_and_copy() -> None:
    image = np.arange(10 * 20 * 3, dtype=np.uint8).reshape(10, 20, 3)
    crop = crop_image(image, BoundingBox(2.5, 1.2, 7.1, 4.0))
    assert crop.shape == (3, 6, 3)
    np.testing.assert_array_equal(crop, image[1:4, 2:8])
    crop[:] = 0
    assert image[1, 2].sum() != 0


def test_crop_outside_raises() -> None:
    with pytest.raises(InvalidEntityError):
        crop_image(np.zeros((10, 10, 3), np.uint8), BoundingBox(20, 20, 30, 30))
