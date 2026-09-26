# 016 - Adaptador: tracker BoT-SORT con compensación de movimiento de cámara

## Objetivo
Implementar `BotSortTracker` (puerto `Tracker`) sobre `trackers.BoTSORTTracker` 2.6.0 con CMC siempre
activo y timestamps en segundos (fps variable).

## Depende de
001, 005.

## Archivos rectores aplicables
- ADR-004 (API verificada y parámetros). RF-04, RF-08. ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/tracking/botsort_tracker.py`
- `tests/unit/adapters/test_botsort_tracker.py`

## Dependencias externas
trackers==2.6.0, supervision==0.30.5, opencv-python==4.14.0.94 (ya instalados).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class Tracker(Protocol):
    def update(self, detections: Sequence[VehicleDetection], image: ImageBGR,
               timestamp_ms: int) -> list[TrackedVehicle]: ...
    def reset(self) -> None: ...
# de domain
@dataclass(frozen=True, slots=True)
class VehicleDetection: box: BoundingBox; confidence: float; vehicle_type: VehicleType
@dataclass(frozen=True, slots=True)
class TrackedVehicle: track_id: int; box: BoundingBox; confidence: float; vehicle_type: VehicleType
class TrackingError(LectorPlacasError): ...
# API verificada de trackers 2.6.0
# from trackers import BoTSORTTracker
# BoTSORTTracker(lost_track_buffer=30, frame_rate=30.0, track_activation_threshold=0.7,
#     minimum_consecutive_frames=2, minimum_iou_threshold_first_assoc=0.2,
#     minimum_iou_threshold_second_assoc=0.5, minimum_iou_threshold_unconfirmed_assoc=0.3,
#     high_conf_det_threshold=0.6, enable_cmc=True, cmc_method="sparseOptFlow", cmc_downscale=2,
#     instant_first_frame_activation=True, ...)
# .update(detections: sv.Detections, frame: np.ndarray | None = None, timestamp: float | None = None) -> sv.Detections
#   (devuelve un subconjunto de las detecciones de entrada con tracker_id; -1 = no confirmado)
# .reset() -> None
# supervision: sv.Detections(xyxy=..., confidence=..., class_id=...), sv.Detections.empty()
```
```python
# adapters/tracking/botsort_tracker.py — a implementar
CLASS_ORDER: Final[tuple[VehicleType, ...]] = (
    VehicleType.CAR, VehicleType.MOTORCYCLE, VehicleType.BUS, VehicleType.TRUCK)

@dataclass(frozen=True, slots=True)
class TrackerSettings:
    lost_track_buffer: int
    frame_rate: float
    track_activation_threshold: float
    minimum_consecutive_frames: int
    minimum_iou_threshold_first_assoc: float
    minimum_iou_threshold_second_assoc: float
    minimum_iou_threshold_unconfirmed_assoc: float
    high_conf_det_threshold: float
    cmc_method: str
    cmc_downscale: int

def to_supervision(detections: Sequence[VehicleDetection]) -> sv.Detections: ...
def from_supervision(tracked: sv.Detections) -> list[TrackedVehicle]: ...

class BotSortTracker:
    def __init__(self, settings: TrackerSettings) -> None: ...
    def update(self, detections: Sequence[VehicleDetection], image: ImageBGR,
               timestamp_ms: int) -> list[TrackedVehicle]: ...
    def reset(self) -> None: ...
```

## Comportamiento esperado
1. `__init__` crea `BoTSORTTracker` pasando todos los campos de `settings` con el mismo nombre, más
   `enable_cmc=True` e `instant_first_frame_activation=True`.
2. `to_supervision`: lista vacía → `sv.Detections.empty()`. Si no: `xyxy` float32 `(N, 4)`,
   `confidence` float32 `(N,)`, `class_id` int `(N,)` con el índice del tipo en `CLASS_ORDER`.
3. `from_supervision`: por cada fila con `tracker_id >= 0` crea `TrackedVehicle(int(tracker_id), BoundingBox(*xyxy), float(confidence), CLASS_ORDER[class_id])`.
   Si `tracker_id` es `None` o el objeto está vacío → `[]`.
4. `update`: `result = tracker.update(to_supervision(detections), frame=image, timestamp=timestamp_ms / 1000.0)`;
   excepciones `ValueError`, `IndexError` o `cv2.error` → `TrackingError("fallo del tracker") from e`.
   Devuelve `from_supervision(result)`.
5. `reset()` llama `tracker.reset()`.

## Casos borde y manejo de errores
- Frames sin detecciones deben llamar igual a `update` (para que el tracker envejezca los tracks).

## Tests de aceptación
```python
# tests/unit/adapters/test_botsort_tracker.py
from __future__ import annotations

import numpy as np

from lector_placas.adapters.tracking.botsort_tracker import (
    BotSortTracker, TrackerSettings, from_supervision, to_supervision,
)
from lector_placas.domain.entities import BoundingBox, VehicleDetection, VehicleType

SETTINGS = TrackerSettings(30, 10.0, 0.7, 2, 0.2, 0.5, 0.3, 0.6, "sparseOptFlow", 2)
BACKGROUND = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)


def det(x: float, y: float, kind: VehicleType = VehicleType.CAR) -> VehicleDetection:
    return VehicleDetection(BoundingBox(x, y, x + 60, y + 40), 0.9, kind)


def test_conversion_roundtrip() -> None:
    sv_dets = to_supervision([det(10, 20, VehicleType.BUS)])
    sv_dets.tracker_id = np.array([4])
    tracked = from_supervision(sv_dets)
    assert tracked[0].track_id == 4
    assert tracked[0].vehicle_type is VehicleType.BUS
    assert tracked[0].box == BoundingBox(10.0, 20.0, 70.0, 60.0)


def test_empty_conversion() -> None:
    assert len(to_supervision([])) == 0


def test_moving_vehicle_keeps_id() -> None:
    tracker = BotSortTracker(SETTINGS)
    ids = []
    for step in range(6):
        result = tracker.update([det(20 + 5 * step, 50)], BACKGROUND, step * 100)
        ids.extend(t.track_id for t in result)
    assert ids and len(set(ids)) == 1
    assert ids[0] >= 0


def test_two_vehicles_get_distinct_ids_and_reset_restarts() -> None:
    tracker = BotSortTracker(SETTINGS)
    first = tracker.update([det(10, 10), det(200, 150, VehicleType.MOTORCYCLE)], BACKGROUND, 0)
    assert len({t.track_id for t in first}) == 2
    assert {t.vehicle_type for t in first} == {VehicleType.CAR, VehicleType.MOTORCYCLE}
    tracker.reset()
    again = tracker.update([det(10, 10)], BACKGROUND, 0)
    assert [t.track_id for t in again] == [0]


def test_empty_frame_is_accepted() -> None:
    tracker = BotSortTracker(SETTINGS)
    tracker.update([det(10, 10)], BACKGROUND, 0)
    assert tracker.update([], BACKGROUND, 100) == []
```

## Fuera de alcance
Gestión del ciclo de vida de los tracks (spec 023).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
