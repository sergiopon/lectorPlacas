# 014 - Adaptador: detector de placas open-image-models (baseline)

## Objetivo
Implementar `OimPlateDetector` (puerto `PlateDetector`) envolviendo `YoloV9Detector` de
open-image-models 0.6.0 con un modelo ONNX local.

## Depende de
011.

## Archivos rectores aplicables
- ADR-002, ADR-013 (se ejecuta sobre el recorte del vehículo). SEG-19 (ruta local, nunca nombre de hub).
- ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/plate_detector_oim.py`
- `tests/unit/adapters/test_plate_detector_oim.py`

## Dependencias externas
open-image-models==0.6.0 (ya instalado).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class PlateDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...
# de domain
@dataclass(frozen=True, slots=True)
class PlateDetection: box: BoundingBox; confidence: float
class InferenceError(LectorPlacasError): ...
class ModelLoadError(LectorPlacasError): ...
# de adapters/inference/onnx_session.py (spec 011)
ORT_ERRORS: Final[tuple[type[BaseException], ...]]
# API verificada de open-image-models 0.6.0
# from open_image_models.detection.core.yolo_v9.inference import YoloV9Detector
# YoloV9Detector(model_path, class_labels, *, conf_thresh=None, batch_size=1, providers=None, sess_options=None)
# YoloV9Detector.predict(image_bgr: np.ndarray) -> list[DetectionResult]
# from open_image_models.detection.core.base import BoundingBox as OimBox, DetectionResult
# DetectionResult(label: str, confidence: float, bounding_box: OimBox); OimBox(x1: int, y1: int, x2: int, y2: int)
```
```python
# adapters/inference/plate_detector_oim.py — a implementar
MIN_SIDE_PX: Final[int] = 16
OIM_CLASS_LABELS: Final[tuple[str, ...]] = ("License Plate",)

class OimDetectorLike(Protocol):
    def predict(self, images: npt.NDArray[np.uint8]) -> list[Any]: ...

class OimPlateDetector:
    def __init__(self, detector: OimDetectorLike) -> None: ...
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...

def create_oim_plate_detector(model_path: Path, score_threshold: float,
                              providers: list[str]) -> OimPlateDetector: ...
```

## Comportamiento esperado
1. `create_oim_plate_detector`: `YoloV9Detector(model_path, OIM_CLASS_LABELS, conf_thresh=score_threshold, providers=providers)`;
   `ORT_ERRORS` o `FileNotFoundError` → `ModelLoadError("no se pudo cargar el detector de placas: <model_path.name>") from e`.
2. `detect(image)`: si `image.shape[0] < MIN_SIDE_PX` o `image.shape[1] < MIN_SIDE_PX` → `[]`.
   `results = detector.predict(image)`; `ORT_ERRORS` → `InferenceError("fallo del detector de placas") from e`.
3. Por cada resultado: `bb = r.bounding_box`; caja `(bb.x1, bb.y1, bb.x2, bb.y2)` convertida a `float` y
   recortada a la imagen con `BoundingBox.clip(width, height)` tras construirla solo si `x2 > x1` e `y2 > y1`
   y `x1 >= 0`, `y1 >= 0` (valores negativos se llevan a 0 antes); se omite si queda vacía.
   `confidence = min(1.0, max(0.0, float(r.confidence)))`.
4. Devuelve las detecciones ordenadas por `confidence` descendente.

## Casos borde y manejo de errores
- Nunca pases `detection_model=<nombre>` (dispararía descargas): solo la ruta local (SEG-19).

## Tests de aceptación
```python
# tests/unit/adapters/test_plate_detector_oim.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from open_image_models.detection.core.base import BoundingBox as OimBox
from open_image_models.detection.core.base import DetectionResult

from lector_placas.adapters.inference.plate_detector_oim import (
    OimPlateDetector, create_oim_plate_detector,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import ModelLoadError

ROOT = Path(__file__).resolve().parents[3]
REAL_MODEL = ROOT / "models" / "oim-yolo-v9-t-384-plates" / "yolo-v9-t-384-license-plates-end2end.onnx"


class FakeOim:
    def __init__(self, results: list[DetectionResult]) -> None:
        self.results = results

    def predict(self, images: np.ndarray) -> list[DetectionResult]:
        return self.results


def result(conf: float, x1: int, y1: int, x2: int, y2: int) -> DetectionResult:
    return DetectionResult("License Plate", conf, OimBox(x1, y1, x2, y2))


def test_converts_clips_and_sorts() -> None:
    fake = FakeOim([result(0.5, 10, 10, 50, 30), result(0.9, -5, 2, 300, 20),
                    result(0.7, 60, 60, 60, 70)])
    detections = OimPlateDetector(fake).detect(np.zeros((40, 100, 3), np.uint8))
    assert [d.confidence for d in detections] == [0.9, 0.5]
    assert detections[0].box == BoundingBox(0.0, 2.0, 100.0, 20.0)
    assert detections[1].box == BoundingBox(10.0, 10.0, 50.0, 30.0)


def test_small_images_return_empty() -> None:
    fake = FakeOim([result(0.9, 0, 0, 5, 5)])
    assert OimPlateDetector(fake).detect(np.zeros((10, 100, 3), np.uint8)) == []


def test_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError):
        create_oim_plate_detector(tmp_path / "no.onnx", 0.25, ["CPUExecutionProvider"])


@pytest.mark.integration
@pytest.mark.skipif(not REAL_MODEL.exists(), reason="modelo no descargado (lector models fetch)")
def test_real_model_runs_on_blank_image() -> None:
    detector = create_oim_plate_detector(REAL_MODEL, 0.25, ["CPUExecutionProvider"])
    assert isinstance(detector.detect(np.zeros((200, 300, 3), np.uint8)), list)
```

## Fuera de alcance
Detector YOLO propio (spec 015).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde (el test real se omite si el modelo no está).
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
