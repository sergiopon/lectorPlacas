# 013 - Adaptador: detector de vehículos YOLO26n (ONNX)

## Objetivo
Implementar `YoloVehicleDetector` (puerto `VehicleDetector`) sobre `YoloEnd2EndOnnxModel`, mapeando
las clases COCO 2, 3, 5, 7 a `car`, `motorcycle`, `bus`, `truck`.

## Depende de
012.

## Archivos rectores aplicables
- ADR-001 (clases COCO usadas), RF-06. ARQUITECTURA.md §4, §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/vehicle_detector_yolo.py`
- `tests/unit/adapters/test_vehicle_detector_yolo.py`

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
```python
# de application/ports.py
class VehicleDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[VehicleDetection]: ...
# de domain/entities.py
class VehicleType(StrEnum): CAR = "car"; MOTORCYCLE = "motorcycle"; BUS = "bus"; TRUCK = "truck"
@dataclass(frozen=True, slots=True)
class VehicleDetection: box: BoundingBox; confidence: float; vehicle_type: VehicleType
# de adapters/inference/yolo_end2end.py (spec 012)
@dataclass(frozen=True, slots=True)
class RawDetection: box: BoundingBox; score: float; class_id: int
class YoloEnd2EndOnnxModel:
    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]: ...
```
```python
# adapters/inference/vehicle_detector_yolo.py — a implementar
COCO_VEHICLE_CLASSES: Final[Mapping[int, VehicleType]] = MappingProxyType(
    {2: VehicleType.CAR, 3: VehicleType.MOTORCYCLE, 5: VehicleType.BUS, 7: VehicleType.TRUCK})

class YoloPredictor(Protocol):
    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]: ...

class YoloVehicleDetector:
    def __init__(self, model: YoloPredictor, score_threshold: float) -> None: ...
    def detect(self, image: ImageBGR) -> list[VehicleDetection]: ...
```

## Comportamiento esperado
1. `__init__`: `score_threshold` en [0, 1] o `InferenceError("umbral inválido")`.
2. `detect(image)`: `model.predict(image, score_threshold)`; conserva solo `class_id` presente en
   `COCO_VEHICLE_CLASSES`; devuelve `VehicleDetection(raw.box, raw.score, tipo)` en el mismo orden (score descendente).

## Casos borde y manejo de errores
- Personas, bicicletas y otras clases COCO se descartan.
- Errores del modelo (`InferenceError`) se propagan sin cambios.

## Tests de aceptación
```python
# tests/unit/adapters/test_vehicle_detector_yolo.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.vehicle_detector_yolo import YoloVehicleDetector
from lector_placas.adapters.inference.yolo_end2end import RawDetection
from lector_placas.domain.entities import BoundingBox, VehicleType
from lector_placas.domain.errors import InferenceError

BOX = BoundingBox(1, 1, 10, 10)


class FakeModel:
    def __init__(self, rows: list[RawDetection]) -> None:
        self.rows = rows
        self.thresholds: list[float] = []

    def predict(self, image: np.ndarray, score_threshold: float) -> list[RawDetection]:
        self.thresholds.append(score_threshold)
        return self.rows


def test_maps_coco_classes_and_drops_others() -> None:
    model = FakeModel([RawDetection(BOX, 0.9, 2), RawDetection(BOX, 0.8, 0),
                       RawDetection(BOX, 0.7, 3), RawDetection(BOX, 0.6, 5),
                       RawDetection(BOX, 0.5, 7), RawDetection(BOX, 0.4, 1)])
    detections = YoloVehicleDetector(model, 0.25).detect(np.zeros((10, 10, 3), np.uint8))
    assert [d.vehicle_type for d in detections] == [
        VehicleType.CAR, VehicleType.MOTORCYCLE, VehicleType.BUS, VehicleType.TRUCK]
    assert [d.confidence for d in detections] == [0.9, 0.7, 0.6, 0.5]
    assert model.thresholds == [0.25]


def test_invalid_threshold() -> None:
    with pytest.raises(InferenceError):
        YoloVehicleDetector(FakeModel([]), 1.5)
```

## Fuera de alcance
Exportar `yolo26n-coco.onnx` (spec 030). Construcción en la composición (spec 028).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
