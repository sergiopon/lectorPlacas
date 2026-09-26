"""Adaptador del detector de vehículos YOLO26n en ONNX (puerto `VehicleDetector`).

Envuelve un modelo YOLO end2end y traduce las clases COCO de vehículos a los tipos del
dominio; el resto de clases (persona, bicicleta, etc.) se descartan (ADR-001).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Protocol

from lector_placas.adapters.inference.yolo_end2end import RawDetection
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import VehicleDetection, VehicleType
from lector_placas.domain.errors import InferenceError

COCO_VEHICLE_CLASSES: Final[Mapping[int, VehicleType]] = MappingProxyType(
    {2: VehicleType.CAR, 3: VehicleType.MOTORCYCLE, 5: VehicleType.BUS, 7: VehicleType.TRUCK}
)


class YoloPredictor(Protocol):
    """Subconjunto de `YoloEnd2EndOnnxModel` usado por el adaptador."""

    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]:
        """Ejecuta la inferencia y devuelve las detecciones crudas del modelo."""
        ...


class YoloVehicleDetector:
    """Detector de vehículos que mapea las clases COCO a tipos del dominio."""

    def __init__(self, model: YoloPredictor, score_threshold: float) -> None:
        """Inicializa el detector con un modelo ya cargado.

        Args:
            model: modelo YOLO end2end que entrega las detecciones crudas.
            score_threshold: umbral mínimo de score, en `[0, 1]`.

        Raises:
            InferenceError: si `score_threshold` no está en `[0, 1]`.
        """
        if not math.isfinite(score_threshold) or not 0.0 <= score_threshold <= 1.0:
            raise InferenceError("umbral inválido")
        self._model = model
        self._score_threshold = score_threshold

    def detect(self, image: ImageBGR) -> list[VehicleDetection]:
        """Detecta vehículos en un frame.

        Args:
            image: frame BGR en el que buscar vehículos.

        Returns:
            Detecciones de vehículos en el orden entregado por el modelo (score
            descendente), descartando las clases COCO que no son vehículos.

        Raises:
            InferenceError: si la inferencia falla; se propaga sin cambios.
        """
        return [
            VehicleDetection(raw.box, raw.score, COCO_VEHICLE_CLASSES[raw.class_id])
            for raw in self._model.predict(image, self._score_threshold)
            if raw.class_id in COCO_VEHICLE_CLASSES
        ]
