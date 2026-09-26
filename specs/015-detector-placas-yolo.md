# 015 - Adaptador: detector de placas YOLO26n fine-tuneado (ONNX)

## Objetivo
Implementar `YoloPlateDetector` (puerto `PlateDetector`) para el modelo propio exportado con una sola
clase `plate` (id 0).

## Depende de
012.

## Archivos rectores aplicables
- ADR-002 (v1.1), ADR-013. ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/plate_detector_yolo.py`
- `tests/unit/adapters/test_plate_detector_yolo.py`

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
```python
# de application/ports.py
class PlateDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...
# de adapters/inference/yolo_end2end.py (spec 012)
@dataclass(frozen=True, slots=True)
class RawDetection: box: BoundingBox; score: float; class_id: int
# de adapters/inference/vehicle_detector_yolo.py (spec 013)
class YoloPredictor(Protocol):
    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]: ...
```
```python
# adapters/inference/plate_detector_yolo.py — a implementar
PLATE_CLASS_ID: Final[int] = 0
MIN_SIDE_PX: Final[int] = 16

class YoloPlateDetector:
    def __init__(self, model: YoloPredictor, score_threshold: float) -> None: ...
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...
```

## Comportamiento esperado
1. `__init__`: umbral en [0, 1] o `InferenceError`.
2. `detect`: imagen con algún lado < `MIN_SIDE_PX` → `[]`. Si no, `model.predict(image, thr)` y conserva
   solo `class_id == PLATE_CLASS_ID` como `PlateDetection(raw.box, raw.score)`, en el orden recibido.

## Casos borde y manejo de errores
- Otras clases se ignoran.

## Tests de aceptación
```python
# tests/unit/adapters/test_plate_detector_yolo.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.plate_detector_yolo import YoloPlateDetector
from lector_placas.adapters.inference.yolo_end2end import RawDetection
from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import InferenceError

BOX = BoundingBox(1, 1, 10, 5)


class FakeModel:
    def predict(self, image: np.ndarray, score_threshold: float) -> list[RawDetection]:
        return [RawDetection(BOX, 0.9, 0), RawDetection(BOX, 0.8, 1), RawDetection(BOX, 0.3, 0)]


def test_keeps_plate_class_only() -> None:
    detections = YoloPlateDetector(FakeModel(), 0.25).detect(np.zeros((32, 32, 3), np.uint8))
    assert detections == [PlateDetection(BOX, 0.9), PlateDetection(BOX, 0.3)]


def test_small_image() -> None:
    assert YoloPlateDetector(FakeModel(), 0.25).detect(np.zeros((8, 32, 3), np.uint8)) == []


def test_invalid_threshold() -> None:
    with pytest.raises(InferenceError):
        YoloPlateDetector(FakeModel(), -0.1)
```

## Fuera de alcance
Entrenamiento y exportación (spec 030).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
