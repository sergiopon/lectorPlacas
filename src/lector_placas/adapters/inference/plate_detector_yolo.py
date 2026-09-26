"""Adaptador del detector de placas YOLO26n propio fine-tuneado (ONNX).

Envuelve un modelo YOLO end2end exportado con una sola clase `plate` (id 0) y conserva
solo las detecciones de esa clase; el resto de clases se descartan (ADR-013).
"""

from __future__ import annotations

from typing import Final

from lector_placas.adapters.inference.vehicle_detector_yolo import YoloPredictor
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import PlateDetection
from lector_placas.domain.errors import InferenceError

PLATE_CLASS_ID: Final[int] = 0
MIN_SIDE_PX: Final[int] = 16


class YoloPlateDetector:
    """Detector de placas que conserva únicamente la clase `plate` del modelo."""

    def __init__(self, model: YoloPredictor, score_threshold: float) -> None:
        """Inicializa el detector con un modelo ya cargado.

        Args:
            model: modelo YOLO end2end que entrega las detecciones crudas.
            score_threshold: umbral mínimo de score, en `[0, 1]`.

        Raises:
            InferenceError: si `score_threshold` no está en `[0, 1]`.
        """
        if not 0.0 <= score_threshold <= 1.0:
            raise InferenceError("umbral inválido")
        self._model = model
        self._score_threshold = score_threshold

    def detect(self, image: ImageBGR) -> list[PlateDetection]:
        """Detecta placas en un frame o en un recorte de vehículo.

        Args:
            image: imagen BGR en la que buscar placas.

        Returns:
            Detecciones de placa en el orden entregado por el modelo, descartando las
            clases distintas de `PLATE_CLASS_ID`; vacío si la imagen es demasiado pequeña.
        """
        height, width = image.shape[0], image.shape[1]
        if height < MIN_SIDE_PX or width < MIN_SIDE_PX:
            return []
        return [
            PlateDetection(raw.box, raw.score)
            for raw in self._model.predict(image, self._score_threshold)
            if raw.class_id == PLATE_CLASS_ID
        ]
