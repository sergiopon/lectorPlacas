"""Operaciones de imagen sin estado usadas por los casos de uso de la aplicación."""

from __future__ import annotations

import math

import numpy as np

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InvalidEntityError


def crop_image(image: ImageBGR, box: BoundingBox) -> ImageBGR:
    """Recorta de `image` la región cubierta por `box`, redondeando hacia fuera.

    Args:
        image: imagen BGR de entrada.
        box: caja en coordenadas de la imagen, con `x1, y1 >= 0`.

    Returns:
        Copia C-contigua de las filas `floor(y1)..ceil(y2)` y columnas `floor(x1)..ceil(x2)`,
        recortada a los límites de la imagen.

    Raises:
        InvalidEntityError: si la región recortada queda vacía.
    """
    height, width = image.shape[0], image.shape[1]
    x0 = max(0, math.floor(box.x1))
    y0 = max(0, math.floor(box.y1))
    x1 = min(int(width), math.ceil(box.x2))
    y1 = min(int(height), math.ceil(box.y2))
    if x1 <= x0 or y1 <= y0:
        raise InvalidEntityError("recorte vacío")
    return np.ascontiguousarray(image[y0:y1, x0:x1]).copy()
