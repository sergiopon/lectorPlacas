# 023 - Aplicación: registro de tracks y recorte de imágenes

## Objetivo
Implementar `TrackRegistry` (ciclo de vida de los tracks, lecturas y mejor recorte) y `crop_image`.

## Depende de
001, 005.

## Archivos rectores aplicables
- ARQUITECTURA.md §3 (pasos 3–6), §2 (application: solo domain + numpy). ADR-006 (lectura dirigida por track).
- docs/02-contratos.md §5; docs/03-modelo-datos.md §2 (mejor recorte = mayor `quality_score × mean_confidence`).

## Archivos a crear/modificar
- `src/lector_placas/application/image_ops.py`
- `src/lector_placas/application/track_registry.py`
- `tests/unit/application/test_image_ops.py`
- `tests/unit/application/test_track_registry.py`

## Dependencias externas
numpy==2.5.3.

## Interfaces y tipos involucrados
```python
# de domain/entities.py
class VehicleType(StrEnum): CAR = "car"; MOTORCYCLE = "motorcycle"; BUS = "bus"; TRUCK = "truck"
@dataclass(frozen=True, slots=True)
class BoundingBox: x1: float; y1: float; x2: float; y2: float
@dataclass(frozen=True, slots=True)
class TrackedVehicle: track_id: int; box: BoundingBox; confidence: float; vehicle_type: VehicleType
@dataclass(frozen=True, slots=True)
class PlateReading: track_id: int; frame_index: int; timestamp_ms: int; text: str; char_confidences: tuple[float, ...]
    plate_box: BoundingBox; detection_confidence: float; quality_score: float
    @property
    def mean_confidence(self) -> float: ...
# de application/ports.py
ImageBGR: TypeAlias = npt.NDArray[np.uint8]
# de domain/errors.py
class InvalidEntityError(DomainError): ...
class ConfigurationError(LectorPlacasError): ...
```
```python
# application/image_ops.py — a implementar
def crop_image(image: ImageBGR, box: BoundingBox) -> ImageBGR: ...

# application/track_registry.py — a implementar
@dataclass(frozen=True, slots=True, eq=False)
class FinalizedTrack:
    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    readings: tuple[PlateReading, ...]
    best_crop: ImageBGR | None

class TrackRegistry:
    def __init__(self, max_readings_per_track: int) -> None: ...
    @property
    def active_count(self) -> int: ...
    def observe(self, tracked: Sequence[TrackedVehicle], timestamp_ms: int) -> None: ...
    def needs_reading(self, track_id: int) -> bool: ...
    def add_reading(self, reading: PlateReading, crop: ImageBGR) -> None: ...
    def pop_inactive(self, now_ms: int, inactive_after_ms: int) -> list[FinalizedTrack]: ...
    def pop_all(self) -> list[FinalizedTrack]: ...
```

## Comportamiento esperado
1. `crop_image(image, box)`: `x0 = max(0, floor(box.x1))`, `y0 = max(0, floor(box.y1))`,
   `x1 = min(ancho, ceil(box.x2))`, `y1 = min(alto, ceil(box.y2))`; si queda vacío → `InvalidEntityError("recorte vacío")`;
   devuelve `np.ascontiguousarray(image[y0:y1, x0:x1]).copy()`.
2. `TrackRegistry.__init__`: `max_readings_per_track >= 1` o `ConfigurationError`. Estado interno por track en una
   dataclass privada mutable `_TrackState` (first_seen_ms, last_seen_ms, votos por tipo `dict[VehicleType, int]`,
   suma de confianza por tipo `dict[VehicleType, float]`, `readings: list[PlateReading]`, `best_crop`, `best_score`).
3. `observe(tracked, ts)`: por cada vehículo crea el estado si no existe (`first_seen_ms = ts`), fija `last_seen_ms = ts`,
   suma 1 voto y su confianza a su tipo.
4. `needs_reading(id)`: `True` si el track existe y tiene menos de `max_readings_per_track` lecturas.
5. `add_reading(reading, crop)`: track inexistente o ya lleno → `InvalidEntityError`. Añade la lectura;
   `score = reading.quality_score * reading.mean_confidence`; si no hay mejor recorte o `score > best_score`
   (estrictamente) → `best_crop = crop.copy()`, `best_score = score`.
6. Tipo final del track: el de más votos; empate → mayor suma de confianza; empate → el primero en el orden de
   declaración de `VehicleType`.
7. `pop_inactive(now_ms, inactive_after_ms)`: extrae los tracks con `now_ms - last_seen_ms > inactive_after_ms`;
   `pop_all()`: extrae todos. Ambos devuelven `FinalizedTrack` ordenados por `track_id` con `readings` en orden de llegada.
8. `active_count` = número de tracks en el registro.

## Casos borde y manejo de errores
- Tras extraer un track, un `observe` con el mismo `track_id` crea un track nuevo (nuevo avistamiento).

## Tests de aceptación
```python
# tests/unit/application/test_image_ops.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.image_ops import crop_image
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InvalidEntityError


def test_crop_floor_ceil_and_copy() -> None:
    image = np.arange(10 * 20 * 3, dtype=np.uint8).reshape(10, 20, 3)
    crop = crop_image(image, BoundingBox(2.5, 1.2, 7.1, 4.0))
    assert crop.shape == (3, 6, 3)
    np.testing.assert_array_equal(crop, image[1:4, 2:8])
    crop[:] = 0
    assert image[1, 2].sum() != 0


def test_crop_outside_raises() -> None:
    with pytest.raises(InvalidEntityError):
        crop_image(np.zeros((10, 10, 3), np.uint8), BoundingBox(20, 20, 30, 30))
```
```python
# tests/unit/application/test_track_registry.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.track_registry import TrackRegistry
from lector_placas.domain.entities import BoundingBox, PlateReading, TrackedVehicle, VehicleType
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError

BOX = BoundingBox(0, 0, 10, 10)


def tv(track_id: int, kind: VehicleType = VehicleType.CAR, conf: float = 0.9) -> TrackedVehicle:
    return TrackedVehicle(track_id, BOX, conf, kind)


def reading(track_id: int, conf: float, quality: float, ts: int = 0) -> PlateReading:
    return PlateReading(track_id, 0, ts, "ABC123", (conf,) * 6, BOX, 0.9, quality)


def crop(value: int) -> np.ndarray:
    return np.full((2, 2, 3), value, np.uint8)


def test_lifecycle_and_ordering() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(5), tv(3)], 0)
    registry.observe([tv(5)], 500)
    assert registry.active_count == 2
    inactive = registry.pop_inactive(now_ms=1200, inactive_after_ms=1000)
    assert [t.track_id for t in inactive] == [3]
    assert (inactive[0].first_seen_ms, inactive[0].last_seen_ms) == (0, 0)
    remaining = registry.pop_all()
    assert [(t.track_id, t.first_seen_ms, t.last_seen_ms) for t in remaining] == [(5, 0, 500)]
    assert registry.active_count == 0


def test_reading_limit_and_best_crop() -> None:
    registry = TrackRegistry(2)
    registry.observe([tv(1)], 0)
    assert registry.needs_reading(1)
    registry.add_reading(reading(1, 0.5, 10.0), crop(1))
    registry.add_reading(reading(1, 0.9, 10.0, ts=100), crop(2))
    assert not registry.needs_reading(1)
    with pytest.raises(InvalidEntityError):
        registry.add_reading(reading(1, 0.9, 99.0), crop(3))
    finalized = registry.pop_all()[0]
    assert [r.timestamp_ms for r in finalized.readings] == [0, 100]
    assert finalized.best_crop is not None and int(finalized.best_crop[0, 0, 0]) == 2


def test_unknown_track_and_needs_reading() -> None:
    registry = TrackRegistry(1)
    assert not registry.needs_reading(9)
    with pytest.raises(InvalidEntityError):
        registry.add_reading(reading(9, 0.9, 1.0), crop(1))


def test_vehicle_type_majority_and_ties() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1, VehicleType.TRUCK, 0.9)], 0)
    registry.observe([tv(1, VehicleType.BUS, 0.6)], 100)
    registry.observe([tv(1, VehicleType.BUS, 0.6)], 200)
    registry.observe([tv(2, VehicleType.TRUCK, 0.5)], 0)
    registry.observe([tv(2, VehicleType.CAR, 0.5)], 100)
    types = {t.track_id: t.vehicle_type for t in registry.pop_all()}
    assert types == {1: VehicleType.BUS, 2: VehicleType.CAR}


def test_track_without_readings_has_no_crop() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1)], 0)
    finalized = registry.pop_all()[0]
    assert finalized.readings == () and finalized.best_crop is None


def test_reappearing_id_is_new_track() -> None:
    registry = TrackRegistry(1)
    registry.observe([tv(1)], 0)
    registry.pop_all()
    registry.observe([tv(1)], 5000)
    assert registry.pop_all()[0].first_seen_ms == 5000


def test_invalid_limit() -> None:
    with pytest.raises(ConfigurationError):
        TrackRegistry(0)
```

## Fuera de alcance
Consolidación y persistencia (spec 024).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
