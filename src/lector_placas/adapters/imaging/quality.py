"""Puntuación de nitidez de recortes de placa mediante la varianza del Laplaciano."""

from __future__ import annotations

from typing import Final

import cv2

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.errors import InferenceError

NORMALIZED_SIZE: Final[tuple[int, int]] = (128, 64)  # (ancho, alto) para cv2.resize


class LaplacianQualityScorer:
    """Puntúa la nitidez con la varianza del Laplaciano sobre la imagen normalizada."""

    def sharpness(self, image: ImageBGR) -> float:
        """Calcula la nitidez de la imagen BGR.

        Args:
            image: recorte BGR de la placa.

        Returns:
            Varianza del Laplaciano de la imagen en gris reescalada a `NORMALIZED_SIZE`.

        Raises:
            InferenceError: si la imagen tiene algún lado de longitud cero.
        """
        height, width = image.shape[:2]
        if height == 0 or width == 0:
            raise InferenceError("imagen vacía")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, NORMALIZED_SIZE, interpolation=cv2.INTER_AREA)
        return float(cv2.Laplacian(resized, cv2.CV_64F).var())
