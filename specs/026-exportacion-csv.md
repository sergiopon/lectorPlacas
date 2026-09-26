# 026 - Aplicación y adaptador: exportación CSV

## Objetivo
Implementar el caso de uso `ExportSightings` y el adaptador `CsvExportStore` (puerto `ExportStore`) que
escribe CSV 0600 en `data/exports/` y borra exportaciones vencidas.

## Depende de
005, 007.

## Archivos rectores aplicables
- docs/03-modelo-datos.md §3 (nombre, cabecera, listas con `|`, inyección CSV). reglas-seguridad.md SEG-04, SEG-08, SEG-13.

## Archivos a crear/modificar
- `src/lector_placas/application/export_sightings.py`
- `src/lector_placas/adapters/export/csv_export_store.py`
- `tests/unit/application/test_export_sightings.py`
- `tests/unit/adapters/test_csv_export_store.py`

## Dependencias externas
Ninguna (stdlib `csv`, `io`).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class PlateRepository(Protocol):
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
class ExportStore(Protocol):
    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
class Clock(Protocol):
    def now(self) -> datetime: ...
# de domain/entities.py: SightingRecord (ver CONTEXT.md), ReviewStatus
# de infrastructure/paths.py
def resolve_within(base: Path, candidate: Path) -> Path: ...
def ensure_private_dir(path: Path) -> Path: ...
# de domain/errors.py
class ExportError(LectorPlacasError): ...
```
```python
# application/export_sightings.py — a implementar
PAGE_SIZE: Final[int] = 500

class ExportSightings:
    def __init__(self, repository: PlateRepository, export_store: ExportStore, clock: Clock) -> None: ...
    def execute(self, status: ReviewStatus | None) -> Path: ...

# adapters/export/csv_export_store.py — a implementar
HEADER: Final[tuple[str, ...]] = (
    "sighting_id", "run_id", "track_id", "first_seen_ms", "last_seen_ms", "vehicle_type",
    "plate_text", "ocr_text", "confidence", "agreement", "num_readings", "status", "reasons",
    "format_ids", "created_at", "reviewed_at")
FILE_GLOB: Final[str] = "sightings-*.csv"

def sanitize_cell(value: str) -> str: ...
def record_to_row(record: SightingRecord) -> list[str]: ...

class CsvExportStore:
    def __init__(self, root: Path) -> None: ...
    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
```

## Comportamiento esperado
1. `ExportSightings.execute(status)`: `now = clock.now()`; pagina `list_sightings(status, PAGE_SIZE, offset)` desde
   `offset = 0` sumando `PAGE_SIZE` hasta recibir menos de `PAGE_SIZE` filas; `path = export_store.write_sightings(todas, now)`;
   `repository.log_event(AuditEvent.EXPORT, now, f"filas={n} archivo={path.name}")`; devuelve `path`.
2. `sanitize_cell(v)`: si `v` empieza por `=`, `+`, `-` o `@` → `"'" + v`; si no, `v`.
3. `record_to_row(r)`: en el orden de `HEADER`; enteros con `str`; `confidence`/`agreement` con `f"{x:.4f}"`;
   enums con `.value`; `reasons` y `format_ids` unidos con `"|"`; fechas con `isoformat(timespec="microseconds")`;
   `reviewed_at` `None` → `""`. Cada celda pasa por `sanitize_cell`.
4. `CsvExportStore.__init__`: guarda `root` (no crea nada todavía).
5. `write_sightings(records, created_at)`: `ensure_private_dir(root)`; nombre
   `f"sightings-{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}.csv"`; `path = resolve_within(root, Path(nombre))`;
   contenido con `csv.writer` (`lineterminator="\n"`) sobre `io.StringIO`: cabecera + filas;
   `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` y escribir en UTF-8.
   `FileExistsError` → `ExportError("ya existe una exportación con ese nombre")`; otro `OSError` → `ExportError`.
6. `delete_older_than(cutoff)`: si `root` no existe → 0; borra archivos `root.glob(FILE_GLOB)` con `st_mtime < cutoff.timestamp()`; devuelve cuántos.

## Casos borde y manejo de errores
- Exportar cero filas produce un CSV solo con cabecera.

## Tests de aceptación
```python
# tests/unit/application/test_export_sightings.py
from __future__ import annotations

from lector_placas.application.export_sightings import PAGE_SIZE, ExportSightings
from lector_placas.application.ports import AuditEvent, RunStart, VideoInfo
from lector_placas.domain.entities import ConsolidatedPlate, ReviewStatus, Sighting, UnverifiedReason, VehicleType
from tests.fixtures.fakes import START, FakeClock, InMemoryExportStore, InMemoryPlateRepository

UNVERIFIED = ConsolidatedPlate("ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED,
                               (UnverifiedReason.LOW_CONFIDENCE,), ())


def test_exports_all_pages_and_audits() -> None:
    repo, store = InMemoryPlateRepository(), InMemoryExportStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track in range(PAGE_SIZE + 3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, UNVERIFIED, None, START))
    path = ExportSightings(repo, store, FakeClock()).execute(ReviewStatus.UNVERIFIED)
    assert len(store.written[0][0]) == PAGE_SIZE + 3
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.EXPORT
    assert detail == f"filas={PAGE_SIZE + 3} archivo={path.name}"
```
```python
# tests/unit/adapters/test_csv_export_store.py
from __future__ import annotations

import csv
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.adapters.export.csv_export_store import (
    HEADER, CsvExportStore, record_to_row, sanitize_cell,
)
from lector_placas.domain.entities import ReviewStatus, SightingRecord, UnverifiedReason, VehicleType
from lector_placas.domain.errors import ExportError

T0 = datetime(2026, 9, 24, 12, 30, 5, tzinfo=UTC)
RECORD = SightingRecord(7, 1, 3, 100, 900, VehicleType.MOTORCYCLE, "XYZ98K", "XYZ98K", 0.912345,
                        0.5, 4, ReviewStatus.UNVERIFIED,
                        (UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_AGREEMENT),
                        ("co_moto",), None, T0, None)


@pytest.mark.parametrize("value,expected", [
    ("=SUM(A1)", "'=SUM(A1)"), ("+1", "'+1"), ("-1", "'-1"), ("@x", "'@x"), ("ABC123", "ABC123"),
])
def test_sanitize_cell(value: str, expected: str) -> None:
    assert sanitize_cell(value) == expected


def test_record_to_row() -> None:
    row = record_to_row(RECORD)
    assert len(row) == len(HEADER)
    assert row[6] == "XYZ98K" and row[8] == "0.9123"
    assert row[12] == "low_confidence|low_agreement"
    assert row[14] == "2026-09-24T12:30:05.000000+00:00" and row[15] == ""


def test_write_creates_private_csv(tmp_path: Path) -> None:
    store = CsvExportStore(tmp_path / "exports")
    path = store.write_sightings([RECORD], T0)
    assert path.name == "sightings-20260924T123005Z.csv"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert tuple(rows[0]) == HEADER and rows[1][0] == "7"
    with pytest.raises(ExportError):
        store.write_sightings([RECORD], T0)


def test_delete_older_than(tmp_path: Path) -> None:
    store = CsvExportStore(tmp_path / "exports")
    assert store.delete_older_than(T0) == 0
    old = store.write_sightings([], T0)
    store.write_sightings([], T0 + timedelta(seconds=1))
    past = (datetime.now(UTC) - timedelta(days=100)).timestamp()
    os.utime(old, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=90)) == 1
    assert not old.exists()
```

## Fuera de alcance
Comando de CLI (spec 028).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
