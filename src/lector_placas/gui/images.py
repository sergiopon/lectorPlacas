"""Conversión de imágenes BGR de OpenCV a `QImage` para los widgets de la GUI (ADR-015)."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.errors import InvalidEntityError

_CHANNELS: int = 3
_DIMENSIONS: int = 3
_INVALID_MESSAGE: str = "la imagen debe ser BGR uint8 de 3 canales"


def bgr_to_qimage(image: ImageBGR) -> QImage:
    """Convierte una imagen BGR de OpenCV en una copia `QImage` en formato RGB888.

    La copia es independiente del arreglo de origen: modificar `image` después de la
    conversión no altera el `QImage` devuelto. No escribe nada a disco.

    Args:
        image: imagen BGR `uint8` de forma (alto, ancho, 3).

    Returns:
        La imagen convertida a RGB, como copia propia.

    Raises:
        InvalidEntityError: si `image` no es tridimensional, no tiene 3 canales o su
            tipo no es `uint8`.
    """
    if image.ndim != _DIMENSIONS or image.shape[2] != _CHANNELS or image.dtype != np.uint8:
        raise InvalidEntityError(_INVALID_MESSAGE)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    qimage = QImage(rgb.data, width, height, _CHANNELS * width, QImage.Format.Format_RGB888)
    return qimage.copy()
