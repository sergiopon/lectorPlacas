"""Adaptador para modelos YOLO con cabeza end2end exportados a ONNX.

La cabeza end2end entrega una salida `output0` de forma `[1, N, 6]` con las filas
`x1, y1, x2, y2, score, class_id` en píxeles del lienzo letterbox (ADR-001). El
decodificador deshace el letterbox, filtra por umbral y ordena por score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy.typing as npt

from lector_placas.adapters.inference.letterbox import (
    LetterboxTransform,
    box_to_source,
    letterbox,
    to_model_input,
)
from lector_placas.adapters.inference.onnx_session import ORT_ERRORS, InferenceSessionLike
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError

INPUT_NAME: Final[str] = "images"
OUTPUT_COLUMNS: Final[int] = 6
OUTPUT_AXES: Final[int] = 3
BATCH_SIZE: Final[int] = 1
INPUT_SIZE_MULTIPLE: Final[int] = 32


@dataclass(frozen=True, slots=True)
class RawDetection:
    """Detección cruda del modelo, antes de mapear la clase a un tipo del dominio.

    Attributes:
        box: caja en coordenadas de la imagen original.
        score: confianza de la detección, en `[0, 1]`.
        class_id: índice de clase tal como lo entrega el modelo.
    """

    box: BoundingBox
    score: float
    class_id: int


def decode_end2end(
    output: npt.NDArray[Any], transform: LetterboxTransform, score_threshold: float
) -> list[RawDetection]:
    """Convierte la salida `[1, N, 6]` de un YOLO end2end en detecciones.

    Args:
        output: salida del modelo con ejes `(lote, filas, columnas)`.
        transform: parámetros del letterbox aplicado antes de la inferencia.
        score_threshold: umbral mínimo de score; las filas por debajo se descartan.

    Returns:
        Detecciones en coordenadas de la imagen original, ordenadas por score descendente
        (orden estable para scores iguales).

    Raises:
        InferenceError: si la forma de `output` no es `[1, N, 6]`.
    """
    if (
        output.ndim != OUTPUT_AXES
        or output.shape[0] != BATCH_SIZE
        or output.shape[2] != OUTPUT_COLUMNS
    ):
        raise InferenceError(f"salida YOLO inesperada: {tuple(output.shape)}")
    detections: list[RawDetection] = []
    for row in output[0]:
        score = float(row[4])
        if not math.isfinite(score) or score < score_threshold:
            continue
        box = box_to_source(float(row[0]), float(row[1]), float(row[2]), float(row[3]), transform)
        if box is None:
            continue
        class_id = round(float(row[5]))
        detections.append(RawDetection(box, min(max(score, 0.0), 1.0), class_id))
    return sorted(detections, key=lambda detection: detection.score, reverse=True)


class YoloEnd2EndOnnxModel:
    """Modelo YOLO end2end en ONNX: letterbox, inferencia y decodificación."""

    def __init__(self, session: InferenceSessionLike, input_size: int) -> None:
        """Inicializa el modelo con una sesión ya creada.

        Args:
            session: sesión de ONNX Runtime del modelo end2end.
            input_size: lado del lienzo cuadrado de entrada; múltiplo de 32.

        Raises:
            InferenceError: si `input_size` no es positivo o no es múltiplo de 32.
        """
        if input_size <= 0 or input_size % INPUT_SIZE_MULTIPLE != 0:
            raise InferenceError("tamaño de entrada inválido")
        self._session = session
        self._input_size = input_size

    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]:
        """Ejecuta el modelo sobre un frame y devuelve sus detecciones.

        Args:
            image: frame BGR de la imagen original.
            score_threshold: umbral mínimo de score; las detecciones por debajo se descartan.

        Returns:
            Detecciones en coordenadas de `image`, ordenadas por score descendente.

        Raises:
            InferenceError: si la inferencia falla.
        """
        letterboxed, transform = letterbox(image, self._input_size)
        tensor = to_model_input(letterboxed)
        try:
            outputs = self._session.run(None, {INPUT_NAME: tensor})
        except ORT_ERRORS as e:
            raise InferenceError("fallo de inferencia YOLO") from e
        return decode_end2end(outputs[0], transform, score_threshold)
