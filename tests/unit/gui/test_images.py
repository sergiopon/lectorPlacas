from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from lector_placas.domain.errors import InvalidEntityError
from lector_placas.gui.images import bgr_to_qimage


def test_bgr_to_qimage_converts_channels() -> None:
    image = np.zeros((4, 3, 3), dtype=np.uint8)
    image[1, 2] = (255, 0, 0)  # BGR: azul puro
    qimage = bgr_to_qimage(image)
    assert qimage.size() == QSize(3, 4)
    assert qimage.format() == QImage.Format.Format_RGB888
    assert qimage.pixelColor(2, 1) == QColor(0, 0, 255)


def test_bgr_to_qimage_is_independent_copy() -> None:
    image = np.full((2, 2, 3), 10, dtype=np.uint8)
    qimage = bgr_to_qimage(image)
    image[:] = 200
    assert qimage.pixelColor(0, 0) == QColor(10, 10, 10)


def test_bgr_to_qimage_rejects_invalid_arrays() -> None:
    with pytest.raises(InvalidEntityError):
        bgr_to_qimage(np.zeros((4, 3), dtype=np.uint8))
    with pytest.raises(InvalidEntityError):
        bgr_to_qimage(np.zeros((4, 3, 4), dtype=np.uint8))
    with pytest.raises(InvalidEntityError):
        bgr_to_qimage(np.zeros((4, 3, 3), dtype=np.float32))
