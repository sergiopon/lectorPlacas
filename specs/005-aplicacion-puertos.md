# 005 - Aplicación: puertos, DTOs, reloj del sistema y fakes de prueba

## Objetivo
Definir los puertos (Protocols) y DTOs de la capa de aplicación, el reloj del sistema y los dobles de
prueba en memoria que usarán los tests de los casos de uso.

## Depende de
001.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 (application solo importa domain y numpy), §4 (tabla de puertos), §6.
- docs/02-contratos.md §4 (firmas literales y tabla de pre/postcondiciones → docstrings).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py`
- `src/lector_placas/infrastructure/clock.py`
- `tests/fixtures/fakes.py`
- `tests/unit/application/__init__.py`
- `tests/unit/application/test_ports.py`
- `tests/unit/infrastructure/__init__.py`
- `tests/unit/infrastructure/test_clock.py`

## Dependencias externas
numpy==2.5.3 (ya instalado).

## Interfaces y tipos involucrados
```python
# de domain/entities.py (spec 001)
PLATE_TEXT_REGEX  # ^[A-Z0-9]{1,10}$
class VehicleType(StrEnum): ...
class ReviewStatus(StrEnum): CONFIRMED; UNVERIFIED; REJECTED; CORRECTED
class VehicleDetection / PlateDetection / TrackedVehicle / OcrResult / PlateReading
class ConsolidatedPlate / Sighting / SightingRecord   # ver CONTEXT.md
# de domain/errors.py
class InvalidEntityError(DomainError): ...
class CropNotFoundError(CropStoreError): ...
class SightingNotFoundError(RepositoryError): ...
```
El contenido de `ports.py` es **exactamente** el de docs/02-contratos.md §4 (bloque de código), con
estos detalles:
- Imports: `from collections.abc import Iterator, Sequence`, `from dataclasses import dataclass`,
  `from datetime import datetime, timedelta`, `from enum import StrEnum`, `from pathlib import Path`,
  `from typing import Protocol, TypeAlias`, `import re`, `import numpy as np`, `import numpy.typing as npt`
  y las entidades del dominio.
- Cada Protocol y cada método lleva docstring con **Precondiciones / Postcondiciones / Raises** tomadas
  de la tabla de docs/02-contratos.md §4.
- Los cuerpos de los métodos de Protocol son `...`.

```python
# infrastructure/clock.py
class SystemClock:
    def now(self) -> datetime: ...   # datetime.now(UTC)
```

## Comportamiento esperado
1. `Frame.__post_init__`: `index >= 0`, `timestamp_ms >= 0`, `image.ndim == 3`, `image.shape[2] == 3`,
   `image.dtype == np.uint8`, `image.shape[0] > 0` y `image.shape[1] > 0`. Si no → `InvalidEntityError`.
   `width = image.shape[1]`, `height = image.shape[0]`.
2. `VideoInfo.__post_init__`: `width > 0`, `height > 0`, `rotation_deg ∈ {0, 90, 180, 270}`,
   `duration_ms is None or duration_ms >= 0`, `average_fps is None or average_fps > 0` (y finito), `codec` no vacío.
3. `RunStart.__post_init__`: `video_sha256` cumple `^[0-9a-f]{64}$`; `profile` no vacío; `started_at` UTC
   (`tzinfo` no nulo y `utcoffset() == timedelta(0)`).
4. `RunStats.__post_init__`: todos los enteros ≥ 0 (`video_duration_ms` puede ser `None`).
   `speed_factor`: `None` si `video_duration_ms is None` o `processing_ms == 0`; si no `video_duration_ms / processing_ms`.
5. `RecordPurge.__post_init__`: conteos ≥ 0.
6. `ReviewDecision.__post_init__`: si `action is ReviewAction.CORRECT`, `corrected_text` debe cumplir `PLATE_TEXT_REGEX`;
   en cualquier otra acción `corrected_text` debe ser `None`. Violación → `InvalidEntityError`.
7. `AuditEvent` y `ReviewAction` con los valores en minúscula de docs/02-contratos.md.
8. `SystemClock.now()` devuelve `datetime.now(UTC)`.
9. `tests/fixtures/fakes.py` con el código literal de abajo.

## Casos borde y manejo de errores
- Todas las validaciones lanzan `InvalidEntityError` con mensaje en español.

## Tests de aceptación
```python
# tests/fixtures/fakes.py
from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lector_placas.application.ports import (
    AuditEvent, ImageBGR, RecordPurge, RunStart, RunStats,
)
from lector_placas.domain.entities import ReviewStatus, Sighting, SightingRecord
from lector_placas.domain.errors import CropNotFoundError, SightingNotFoundError

START = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
LINKED = (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED)


class FakeClock:
    def __init__(self, start: datetime = START, step_ms: int = 0) -> None:
        self.current = start
        self.step = timedelta(milliseconds=step_ms)

    def now(self) -> datetime:
        value = self.current
        self.current = self.current + self.step
        return value


class FakeKeyProvider:
    def __init__(self, key: bytes = bytes(range(32))) -> None:
        self.key = key

    def master_key(self) -> bytes:
        return self.key


class InMemoryCropStore:
    def __init__(self) -> None:
        self.images: dict[str, ImageBGR] = {}
        self.swept_before: list[datetime] = []
        self._counter = itertools.count(1)

    def save(self, image: ImageBGR) -> str:
        ref = f"{next(self._counter):032x}"
        self.images[ref] = image.copy()
        return ref

    def load(self, crop_ref: str) -> ImageBGR:
        if crop_ref not in self.images:
            raise CropNotFoundError("recorte no encontrado")
        return self.images[crop_ref].copy()

    def delete(self, crop_ref: str) -> None:
        self.images.pop(crop_ref, None)

    def delete_older_than(self, cutoff: datetime) -> int:
        self.swept_before.append(cutoff)
        return 0


class InMemoryExportStore:
    def __init__(self, files_to_delete: int = 0) -> None:
        self.written: list[tuple[tuple[SightingRecord, ...], datetime]] = []
        self.deleted_before: list[datetime] = []
        self.files_to_delete = files_to_delete

    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path:
        self.written.append((tuple(records), created_at))
        return Path(f"sightings-{len(self.written)}.csv")

    def delete_older_than(self, cutoff: datetime) -> int:
        self.deleted_before.append(cutoff)
        return self.files_to_delete


@dataclass
class StoredRun:
    start: RunStart
    stats: RunStats | None = None
    finished_at: datetime | None = None
    succeeded: bool | None = None


class InMemoryPlateRepository:
    def __init__(self) -> None:
        self.runs: dict[int, StoredRun] = {}
        self.records: dict[int, SightingRecord] = {}
        self.plates: set[str] = set()
        self.events: list[tuple[AuditEvent, datetime, str]] = []
        self.closed = False
        self._run_ids = itertools.count(1)
        self._sighting_ids = itertools.count(1)

    def start_run(self, run: RunStart) -> int:
        run_id = next(self._run_ids)
        self.runs[run_id] = StoredRun(run)
        self.log_event(AuditEvent.RUN_STARTED, run.started_at, f"run_id={run_id}")
        return run_id

    def finish_run(self, run_id: int, stats: RunStats, finished_at: datetime,
                   succeeded: bool) -> None:
        run = self.runs[run_id]
        run.stats, run.finished_at, run.succeeded = stats, finished_at, succeeded
        status = "completed" if succeeded else "failed"
        self.log_event(AuditEvent.RUN_FINISHED, finished_at, f"run_id={run_id} status={status}")

    def save_sighting(self, sighting: Sighting) -> int:
        sighting_id = next(self._sighting_ids)
        plate = sighting.plate
        self.records[sighting_id] = SightingRecord(
            sighting_id, sighting.run_id, sighting.track_id, sighting.first_seen_ms,
            sighting.last_seen_ms, sighting.vehicle_type, plate.text, plate.text,
            plate.confidence, plate.agreement, plate.num_readings, plate.status, plate.reasons,
            plate.format_ids, sighting.crop_ref, sighting.created_at, None,
        )
        if plate.status is ReviewStatus.CONFIRMED:
            self.plates.add(plate.text)
        return sighting_id

    def list_sightings(self, status: ReviewStatus | None, limit: int,
                       offset: int) -> list[SightingRecord]:
        rows = [r for _, r in sorted(self.records.items()) if status is None or r.status is status]
        return rows[offset: offset + limit]

    def get_sighting(self, sighting_id: int) -> SightingRecord:
        if sighting_id not in self.records:
            raise SightingNotFoundError(f"sighting_id={sighting_id}")
        return self.records[sighting_id]

    def record_review(self, sighting_id: int, status: ReviewStatus, corrected_text: str | None,
                      reviewed_at: datetime) -> None:
        record = self.get_sighting(sighting_id)
        text = corrected_text if corrected_text is not None else record.plate_text
        self.records[sighting_id] = replace(record, status=status, plate_text=text,
                                            reviewed_at=reviewed_at)
        if status in LINKED:
            self.plates.add(text)

    def expire_crop_refs(self, cutoff: datetime) -> list[str]:
        refs: list[str] = []
        for sighting_id, record in sorted(self.records.items()):
            if record.created_at < cutoff and record.crop_ref is not None:
                refs.append(record.crop_ref)
                self.records[sighting_id] = replace(record, crop_ref=None)
        return refs

    def delete_records_before(self, cutoff: datetime) -> RecordPurge:
        old = sorted(sid for sid, r in self.records.items() if r.created_at < cutoff)
        refs = tuple(ref for sid in old if (ref := self.records[sid].crop_ref) is not None)
        for sighting_id in old:
            del self.records[sighting_id]
        live_runs = {r.run_id for r in self.records.values()}
        dead_runs = [rid for rid, run in self.runs.items()
                     if run.start.started_at < cutoff and rid not in live_runs]
        for run_id in dead_runs:
            del self.runs[run_id]
        live_texts = {r.plate_text for r in self.records.values() if r.status in LINKED}
        dead_plates = self.plates - live_texts
        self.plates -= dead_plates
        return RecordPurge(len(old), len(dead_runs), len(dead_plates), refs)

    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None:
        self.events.append((event, occurred_at, detail))

    def close(self) -> None:
        self.closed = True
```
```python
# tests/unit/application/test_ports.py
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from lector_placas.application.ports import (
    AuditEvent, CropStore, ExportStore, Frame, KeyProvider, PlateRepository, RecordPurge,
    ReviewAction, ReviewDecision, RunStart, RunStats, VideoInfo,
)
from lector_placas.domain.errors import InvalidEntityError
from tests.fixtures.fakes import (
    FakeKeyProvider, InMemoryCropStore, InMemoryExportStore, InMemoryPlateRepository,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, 10_000, 30.0, "h264")


def test_frame_properties_and_validation() -> None:
    frame = Frame(0, 0, np.zeros((4, 6, 3), dtype=np.uint8))
    assert (frame.width, frame.height) == (6, 4)
    with pytest.raises(InvalidEntityError):
        Frame(0, 0, np.zeros((4, 6), dtype=np.uint8))
    with pytest.raises(InvalidEntityError):
        Frame(0, 0, np.zeros((4, 6, 3), dtype=np.float32))
    with pytest.raises(InvalidEntityError):
        Frame(-1, 0, np.zeros((4, 6, 3), dtype=np.uint8))


@pytest.mark.parametrize("kwargs", [
    {"width": 0}, {"rotation_deg": 45}, {"duration_ms": -1}, {"average_fps": 0.0}, {"codec": ""},
])
def test_video_info_validation(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = dict(width=10, height=10, rotation_deg=0, duration_ms=None,
                                     average_fps=None, codec="h264")
    values.update(kwargs)
    with pytest.raises(InvalidEntityError):
        VideoInfo(**values)  # type: ignore[arg-type]


def test_run_start_validation() -> None:
    RunStart("a" * 64, "calle_lenta", INFO, NOW)
    with pytest.raises(InvalidEntityError):
        RunStart("A" * 64, "calle_lenta", INFO, NOW)
    with pytest.raises(InvalidEntityError):
        RunStart("a" * 64, "calle_lenta", INFO, NOW.replace(tzinfo=None))


def test_run_stats_speed_factor() -> None:
    assert RunStats(1, 1, 0, 0, 0, 0, 5_000, 10_000).speed_factor == pytest.approx(2.0)
    assert RunStats(1, 1, 0, 0, 0, 0, 0, 10_000).speed_factor is None
    assert RunStats(1, 1, 0, 0, 0, 0, 10, None).speed_factor is None
    with pytest.raises(InvalidEntityError):
        RunStats(-1, 1, 0, 0, 0, 0, 10, None)


def test_record_purge_validation() -> None:
    assert RecordPurge(0, 0, 0, ()).crop_refs == ()
    with pytest.raises(InvalidEntityError):
        RecordPurge(-1, 0, 0, ())


def test_review_decision_rules() -> None:
    assert ReviewDecision(ReviewAction.CORRECT, "ABC123").corrected_text == "ABC123"
    assert ReviewDecision(ReviewAction.SKIP).corrected_text is None
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CORRECT, None)
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CORRECT, "abc")
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CONFIRM, "ABC123")


def test_enum_values() -> None:
    assert [e.value for e in AuditEvent] == [
        "run_started", "run_finished", "review", "purge", "export"]
    assert [a.value for a in ReviewAction] == ["confirm", "correct", "reject", "skip", "quit"]


def test_fakes_satisfy_protocols() -> None:
    repository: PlateRepository = InMemoryPlateRepository()
    crops: CropStore = InMemoryCropStore()
    exports: ExportStore = InMemoryExportStore()
    keys: KeyProvider = FakeKeyProvider()
    assert repository.start_run(RunStart("a" * 64, "p", INFO, NOW)) == 1
    assert len(keys.master_key()) == 32
    assert crops.save(np.zeros((2, 2, 3), dtype=np.uint8)) == f"{1:032x}"
    assert exports.delete_older_than(NOW) == 0
```
```python
# tests/unit/infrastructure/test_clock.py
from __future__ import annotations

from datetime import timedelta

from lector_placas.infrastructure.clock import SystemClock


def test_system_clock_returns_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
```

## Fuera de alcance
Implementaciones de los puertos (specs posteriores).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `ports.py` no importa nada de `adapters`, `infrastructure` ni `cli`.
