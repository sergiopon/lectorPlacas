"""Adaptador del puerto `PlateReader` sobre fast-plate-ocr (ADR-003, SEG-19).

El modelo y su configuración se cargan siempre desde rutas locales ya verificadas;
nunca se usa `hub_ocr_model`, que descargaría de internet en runtime.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, Protocol, cast

import cv2
import numpy as np
import numpy.typing as npt
from fast_plate_ocr import LicensePlateRecognizer

from lector_placas.adapters.inference.onnx_session import ORT_ERRORS
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import OCR_TEXT_REGEX, OcrResult
from lector_placas.domain.errors import InferenceError, ModelLoadError

PAD_CHAR: Final[str] = "_"
LOAD_ERRORS: Final[tuple[type[BaseException], ...]] = (*ORT_ERRORS, FileNotFoundError, TypeError)


class RecognizerLike(Protocol):
    """Subconjunto de `LicensePlateRecognizer` usado por el proyecto."""

    @property
    def config(self) -> Any:  # noqa: ANN401 — la configuración la expone la librería
        """Configuración del modelo; incluye `image_color_mode`."""
        ...

    def run(
        self,
        source: list[npt.NDArray[np.uint8]],
        return_confidence: bool = ...,
    ) -> list[Any]:
        """Ejecuta el OCR sobre una lista de imágenes ya en el color esperado."""
        ...


class FastPlateOcrReader:
    """Lee el texto de recortes de placa con un reconocedor de fast-plate-ocr."""

    def __init__(self, recognizer: RecognizerLike) -> None:
        """Inicializa el lector con un reconocedor ya construido.

        Args:
            recognizer: reconocedor (real o doble de prueba) que implementa `RecognizerLike`.
        """
        self._recognizer = recognizer

    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]:
        """Lee en lote las imágenes de placa recibidas.

        Args:
            plate_images: lista (posiblemente vacía) de recortes BGR.

        Returns:
            Un `OcrResult` por imagen, en el mismo orden; los textos inválidos van vacíos.

        Raises:
            InferenceError: si el modo de color no es soportado, la inferencia falla o el
                OCR devuelve un número de resultados distinto, o sin confianzas.
        """
        if not plate_images:
            return []
        images = self._convert_colors(plate_images)
        try:
            predictions = self._recognizer.run(images, return_confidence=True)
        except ORT_ERRORS as e:
            raise InferenceError("fallo del OCR") from e
        if len(predictions) != len(plate_images):
            raise InferenceError("el OCR devolvió un número de resultados distinto")
        return [self._to_result(prediction) for prediction in predictions]

    def _convert_colors(self, plate_images: Sequence[ImageBGR]) -> list[npt.NDArray[np.uint8]]:
        mode = self._recognizer.config.image_color_mode
        if mode == "rgb":
            conversion = cv2.COLOR_BGR2RGB
        elif mode == "grayscale":
            conversion = cv2.COLOR_BGR2GRAY
        else:
            raise InferenceError("modo de color no soportado")
        return [
            cast(npt.NDArray[np.uint8], cv2.cvtColor(image, conversion)) for image in plate_images
        ]

    @staticmethod
    def _to_result(prediction: Any) -> OcrResult:  # noqa: ANN401 — tipo de la librería
        text = prediction.plate
        probs = prediction.char_probs
        if probs is None:
            raise InferenceError("el OCR no devolvió confianzas por carácter")
        if PAD_CHAR in text or OCR_TEXT_REGEX.fullmatch(text) is None:
            return OcrResult("", ())
        confidences = tuple(min(1.0, max(0.0, float(p))) for p in probs[: len(text)])
        return OcrResult(text, confidences)


def create_fast_plate_ocr_reader(
    onnx_model_path: Path, plate_config_path: Path, providers: list[str]
) -> FastPlateOcrReader:
    """Construye un lector OCR con el modelo y la configuración locales.

    Args:
        onnx_model_path: ruta al modelo ONNX ya verificado.
        plate_config_path: ruta a la configuración de placa del modelo.
        providers: proveedores de ejecución de ONNX Runtime, en orden de preferencia.

    Returns:
        Lector listo para usar.

    Raises:
        ModelLoadError: si la librería no puede cargar el modelo o la configuración.
    """
    try:
        recognizer = LicensePlateRecognizer(
            onnx_model_path=onnx_model_path,
            plate_config_path=plate_config_path,
            providers=providers,
        )
    except LOAD_ERRORS as e:
        raise ModelLoadError(f"no se pudo cargar el OCR: {onnx_model_path.name}") from e
    return FastPlateOcrReader(recognizer)
