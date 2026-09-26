# 025 - Aplicación: purga por retención

## Objetivo
Implementar `PurgeExpiredData`: borra registros de más de `records_days`, recortes de más de
`crops_days` (incluidos archivos huérfanos) y exportaciones vencidas, y lo registra en auditoría.

## Depende de
005.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-03 (retención y ejecución automática), SEG-05 (`detail` sin placas). ADR-005 (Ley 1581).
- docs/03-modelo-datos.md §1–§3.

## Archivos a crear/modificar
- `src/lector_placas/application/purge_expired.py`
- `tests/unit/application/test_purge_expired.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
class PlateRepository(Protocol):
    def expire_crop_refs(self, cutoff: datetime) -> list[str]: ...
    def delete_records_before(self, cutoff: datetime) -> RecordPurge: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
class CropStore(Protocol):
    def delete(self, crop_ref: str) -> None: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
class ExportStore(Protocol):
    def delete_older_than(self, cutoff: datetime) -> int: ...
class Clock(Protocol):
    def now(self) -> datetime: ...
@dataclass(frozen=True, slots=True)
class RecordPurge: sightings_deleted: int; runs_deleted: int; plates_deleted: int; crop_refs: tuple[str, ...]
class AuditEvent(StrEnum): ... PURGE = "purge"
# de domain/errors.py
class ConfigurationError(LectorPlacasError): ...
```
```python
# application/purge_expired.py — a implementar
@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    crops_days: int
    records_days: int

@dataclass(frozen=True, slots=True)
class PurgeResult:
    crops_deleted: int
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    exports_deleted: int

class PurgeExpiredData:
    def __init__(self, repository: PlateRepository, crop_store: CropStore,
                 export_store: ExportStore, clock: Clock, policy: RetentionPolicy) -> None: ...
    def execute(self) -> PurgeResult: ...
```

## Comportamiento esperado
1. `RetentionPolicy.__post_init__`: `1 <= crops_days <= records_days` o `ConfigurationError`.
2. `execute()`, en este orden:
   1. `now = clock.now()`; `records_cutoff = now - timedelta(days=records_days)`; `crops_cutoff = now - timedelta(days=crops_days)`.
   2. `purge = repository.delete_records_before(records_cutoff)`.
   3. `expired = repository.expire_crop_refs(crops_cutoff)`.
   4. Para cada ref de `sorted(set(purge.crop_refs) | set(expired))`: `crop_store.delete(ref)`.
   5. `swept = crop_store.delete_older_than(crops_cutoff)`.
   6. `exports = export_store.delete_older_than(records_cutoff)`.
   7. `result = PurgeResult(len(refs) + swept, purge.sightings_deleted, purge.runs_deleted, purge.plates_deleted, exports)`.
   8. `repository.log_event(AuditEvent.PURGE, now, f"recortes={..} avistamientos={..} corridas={..} placas={..} exportaciones={..}")`.
   9. `logger.info` con los mismos conteos; devuelve `result`.

## Casos borde y manejo de errores
- Errores de los puertos se propagan (la CLI los traduce a código de salida).

## Tests de aceptación
```python
# tests/unit/application/test_purge_expired.py
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from lector_placas.application.ports import AuditEvent, RunStart, VideoInfo
from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.entities import ConsolidatedPlate, ReviewStatus, Sighting, VehicleType
from lector_placas.domain.errors import ConfigurationError
from tests.fixtures.fakes import (
    START, FakeClock, InMemoryCropStore, InMemoryExportStore, InMemoryPlateRepository,
)

PLATE = ConsolidatedPlate("ABC123", 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())
INFO = VideoInfo(10, 10, 0, None, None, "h264")


def seed(repo: InMemoryPlateRepository, crops: InMemoryCropStore, age_days: int, track: int) -> str:
    at = START - timedelta(days=age_days)
    run_id = repo.start_run(RunStart("a" * 64, "p", INFO, at))
    ref = crops.save(np.zeros((2, 2, 3), np.uint8))
    repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, PLATE, ref, at))
    return ref


def test_purges_by_age() -> None:
    repo, crops, exports = InMemoryPlateRepository(), InMemoryCropStore(), InMemoryExportStore(2)
    old = seed(repo, crops, 100, 1)
    mid = seed(repo, crops, 40, 2)
    new = seed(repo, crops, 1, 3)
    result = PurgeExpiredData(repo, crops, exports, FakeClock(), RetentionPolicy(30, 90)).execute()
    assert (result.crops_deleted, result.sightings_deleted, result.runs_deleted) == (2, 1, 1)
    assert result.exports_deleted == 2
    assert set(crops.images) == {new}
    assert old not in crops.images and mid not in crops.images
    assert [r.track_id for r in repo.list_sightings(None, 10, 0)] == [2, 3]
    assert crops.swept_before == [START - timedelta(days=30)]
    assert exports.deleted_before == [START - timedelta(days=90)]
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.PURGE
    assert "ABC123" not in detail and "recortes=2" in detail


def test_nothing_to_purge() -> None:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    seed(repo, crops, 1, 1)
    result = PurgeExpiredData(repo, crops, InMemoryExportStore(), FakeClock(),
                              RetentionPolicy(30, 90)).execute()
    assert (result.crops_deleted, result.sightings_deleted, result.exports_deleted) == (0, 0, 0)


@pytest.mark.parametrize("crops_days,records_days", [(0, 90), (91, 90)])
def test_invalid_policy(crops_days: int, records_days: int) -> None:
    with pytest.raises(ConfigurationError):
        RetentionPolicy(crops_days, records_days)
```

## Fuera de alcance
Invocación automática al inicio de cada comando (spec 028).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
