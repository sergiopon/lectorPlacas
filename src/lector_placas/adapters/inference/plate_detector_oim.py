"""Adaptador del detector de placas basado en open-image-models (YOLOv9 ONNX)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import numpy.typing as npt
from open_image_models.detection.core.base import DetectionResult
from open_image_models.detection.core.yolo_v9.inference import YoloV9Detector

from lector_placas.adapters.inference.onnx_session import ORT_ERRORS
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import InferenceError, ModelLoadError

MIN_SIDE_PX: Final[int] = 16
OIM_CLASS_LABELS: Final[tuple[str, ...]] = ("License Plate",)
_LOAD_ERRORS: Final[tuple[type[BaseException], ...]] = (*ORT_ERRORS, FileNotFoundError)


def _to_detection(result: DetectionResult, width: int, height: int) -> PlateDetection | None:
    """Convierte un `DetectionResult` de open-image-models a `PlateDetection`."""
    bb = result.bounding_box
    x1 = max(0.0, float(bb.x1))
    y1 = max(0.0, float(bb.y1))
    x2 = float(bb.x2)
    y2 = float(bb.y2)
    if x2 <= x1 or y2 <= y1:
        return None
    box = BoundingBox(x1, y1, x2, y2).clip(width, height)
    if box is None:
        return None
    confidence = min(1.0, max(0.0, float(result.confidence)))
    return PlateDetection(box=box, confidence=confidence)


class OimDetectorLike(Protocol):
    """Subconjunto de `YoloV9Detector` usado por el adaptador."""

    def predict(self, images: npt.NDArray[np.uint8]) -> list[Any]:
        """Ejecuta la inferencia y devuelve las detecciones crudas."""
        ...


class OimPlateDetector:
    """Detector de placas que envuelve un `YoloV9Detector` de open-image-models."""

    def __init__(self, detector: OimDetectorLike) -> None:
        """Guarda el detector subyacente ya cargado."""
        self._detector = detector

    def detect(self, image: ImageBGR) -> list[PlateDetection]:
        """Detecta placas en el recorte del vehículo.

        Args:
            image: recorte del vehículo en BGR.

        Returns:
            Detecciones ordenadas por confianza descendente.

        Raises:
            InferenceError: si falla la inferencia de ONNX Runtime.
        """
        height, width = image.shape[0], image.shape[1]
        if height < MIN_SIDE_PX or width < MIN_SIDE_PX:
            return []
        try:
            results = self._detector.predict(image)
        except ORT_ERRORS as e:
            raise InferenceError("fallo del detector de placas") from e

        detections = [
            detection
            for result in results
            if (detection := _to_detection(result, width, height)) is not None
        ]
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections


def create_oim_plate_detector(
    model_path: Path, score_threshold: float, providers: list[str]
) -> OimPlateDetector:
    """Crea un `OimPlateDetector` a partir de un modelo ONNX local ya verificado.

    Args:
        model_path: ruta local al modelo `.onnx` (nunca un nombre del hub, SEG-19).
        score_threshold: umbral mínimo de confianza para las detecciones.
        providers: proveedores de ejecución de ONNX Runtime, en orden de preferencia.

    Returns:
        Detector de placas listo para usar.

    Raises:
        ModelLoadError: si el modelo no se puede cargar.
    """
    try:
        detector = YoloV9Detector(
            model_path,
            OIM_CLASS_LABELS,
            conf_thresh=score_threshold,
            providers=providers,
        )
    except _LOAD_ERRORS as e:
        raise ModelLoadError(f"no se pudo cargar el detector de placas: {model_path.name}") from e
    return OimPlateDetector(detector)
