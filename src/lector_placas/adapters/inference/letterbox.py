"""Pre/post-procesamiento letterbox usado por los modelos YOLO en ONNX."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
import numpy.typing as npt

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError

PAD_VALUE: Final[int] = 114


@dataclass(frozen=True, slots=True)
class LetterboxTransform:
    """Parámetros para deshacer un letterbox sobre una imagen fuente."""

    scale: float
    pad_x: int
    pad_y: int
    source_width: int
    source_height: int


def letterbox(image: ImageBGR, size: int) -> tuple[ImageBGR, LetterboxTransform]:
    """Redimensiona `image` manteniendo el aspecto y la centra en un lienzo cuadrado.

    Args:
        image: imagen BGR de entrada.
        size: lado del lienzo cuadrado de salida.

    Returns:
        Tupla `(lienzo, transform)` con el lienzo `(size, size, 3)` y los parámetros
        para deshacer el letterbox sobre coordenadas de la fuente.

    Raises:
        InferenceError: si `size` no es positivo.
    """
    if size <= 0:
        raise InferenceError("tamaño de entrada inválido")
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x = (size - new_w) // 2
    pad_y = (size - new_h) // 2
    canvas = np.full((size, size, 3), PAD_VALUE, dtype=np.uint8)
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, LetterboxTransform(scale, pad_x, pad_y, w, h)


def to_model_input(letterboxed: ImageBGR) -> npt.NDArray[np.float32]:
    """Convierte una imagen letterboxed BGR en un tensor `(1, 3, S, S)` float32 RGB.

    Args:
        letterboxed: imagen BGR con letterbox aplicado.

    Returns:
        Arreglo C-contiguo `float32` en `[0, 1]`, con orden RGB y ejes
        `(batch, canal, alto, ancho)`.
    """
    rgb = letterboxed[:, :, ::-1]
    normalized = rgb.astype(np.float32) / 255.0
    chw = normalized.transpose(2, 0, 1)
    batched = chw[np.newaxis, ...]
    return np.ascontiguousarray(batched, dtype=np.float32)


def box_to_source(
    x1: float, y1: float, x2: float, y2: float, transform: LetterboxTransform
) -> BoundingBox | None:
    """Deshace el letterbox sobre una caja y la recorta a la imagen fuente.

    Args:
        x1: coordenada x1 en el espacio del lienzo.
        y1: coordenada y1 en el espacio del lienzo.
        x2: coordenada x2 en el espacio del lienzo.
        y2: coordenada y2 en el espacio del lienzo.
        transform: parámetros del letterbox aplicado.

    Returns:
        Caja en coordenadas de la imagen fuente, o `None` si no es finita o queda vacía.
    """
    sx1 = (x1 - transform.pad_x) / transform.scale
    sy1 = (y1 - transform.pad_y) / transform.scale
    sx2 = (x2 - transform.pad_x) / transform.scale
    sy2 = (y2 - transform.pad_y) / transform.scale
    if not all(math.isfinite(v) for v in (sx1, sy1, sx2, sy2)):
        return None
    sx1 = min(max(sx1, 0.0), float(transform.source_width))
    sy1 = min(max(sy1, 0.0), float(transform.source_height))
    sx2 = min(max(sx2, 0.0), float(transform.source_width))
    sy2 = min(max(sy2, 0.0), float(transform.source_height))
    if sx2 <= sx1 or sy2 <= sy1:
        return None
    return BoundingBox(sx1, sy1, sx2, sy2)
