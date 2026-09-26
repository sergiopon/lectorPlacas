# 020 - Adaptador: repositorio SQLCipher

## Objetivo
Implementar `SqlCipherPlateRepository` (puerto `PlateRepository`) sobre una BD SQLCipher cifrada con
la subclave HKDF, con el esquema de docs/03-modelo-datos.md §1.

## Depende de
001, 005, 008.

## Archivos rectores aplicables
- ADR-005. docs/03-modelo-datos.md §1 (esquema literal y tabla "Semántica de escritura").
- reglas-seguridad.md SEG-01, SEG-04 (0600), SEG-05 (`detail` sin placas), SEG-06, SEG-15 (solo `?`; excepción `PRAGMA key`), SEG-16.
- ARQUITECTURA.md §6 (funciones ≤ 20 sentencias: usa helpers privados por operación).

## Archivos a crear/modificar
- `src/lector_placas/adapters/persistence/schema.sql` (bloque SQL literal de docs/03-modelo-datos.md §1)
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py`
- `tests/integration/test_sqlcipher_repository.py`

## Dependencias externas
sqlcipher3==0.6.2 (módulo `sqlcipher3.dbapi2`, API compatible con `sqlite3`), cryptography==50.0.1.

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
@dataclass(frozen=True, slots=True)
class VideoInfo: width: int; height: int; rotation_deg: int; duration_ms: int | None; average_fps: float | None; codec: str
@dataclass(frozen=True, slots=True)
class RunStart: video_sha256: str; profile: str; video: VideoInfo; started_at: datetime
@dataclass(frozen=True, slots=True)
class RunStats: frames_decoded: int; frames_processed: int; tracks_total: int; sightings_confirmed: int
    sightings_unverified: int; tracks_without_reading: int; processing_ms: int; video_duration_ms: int | None
@dataclass(frozen=True, slots=True)
class RecordPurge: sightings_deleted: int; runs_deleted: int; plates_deleted: int; crop_refs: tuple[str, ...]
class AuditEvent(StrEnum): RUN_STARTED="run_started"; RUN_FINISHED="run_finished"; REVIEW="review"; PURGE="purge"; EXPORT="export"
class KeyProvider(Protocol):
    def master_key(self) -> bytes: ...
class PlateRepository(Protocol):
    def start_run(self, run: RunStart) -> int: ...
    def finish_run(self, run_id: int, stats: RunStats, finished_at: datetime, succeeded: bool) -> None: ...
    def save_sighting(self, sighting: Sighting) -> int: ...
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
    def get_sighting(self, sighting_id: int) -> SightingRecord: ...
    def record_review(self, sighting_id: int, status: ReviewStatus, corrected_text: str | None, reviewed_at: datetime) -> None: ...
    def expire_crop_refs(self, cutoff: datetime) -> list[str]: ...
    def delete_records_before(self, cutoff: datetime) -> RecordPurge: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
    def close(self) -> None: ...
# de domain/entities.py: Sighting, SightingRecord, ConsolidatedPlate, ReviewStatus, UnverifiedReason,
#   VehicleType, PLATE_TEXT_REGEX (ver CONTEXT.md)
# de infrastructure/crypto.py (spec 008)
class KeyPurpose(StrEnum): SQLCIPHER = "lector-placas/sqlcipher/v1"; CROPS = "lector-placas/crops/v1"
def derive_key(master_key: bytes, purpose: KeyPurpose) -> bytes: ...
# de domain/errors.py
class RepositoryError, SightingNotFoundError(RepositoryError), EncryptionError
```
```python
# adapters/persistence/sqlcipher_repository.py — a implementar
SCHEMA_VERSION: Final[int] = 1
MAX_PAGE: Final[int] = 10_000
HEX_KEY_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

def to_db_time(value: datetime) -> str: ...     # value.astimezone(UTC).isoformat(timespec="microseconds")
def from_db_time(value: str) -> datetime: ...   # datetime.fromisoformat(value)

class SqlCipherPlateRepository:
    def __init__(self, db_path: Path, key_provider: KeyProvider) -> None: ...
    # + todos los métodos de PlateRepository con las firmas exactas de arriba
```

## Comportamiento esperado
1. **Apertura** (`__init__`, en helpers privados):
   1. Si `db_path` no existe: crearlo vacío con `os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)` y cerrarlo.
   2. `connection = sqlcipher3.dbapi2.connect(str(db_path))`.
   3. `key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()`; si no cumple `HEX_KEY_REGEX` → `EncryptionError`.
      `connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")` con el comentario `# SEG-15: única excepción, hex validado`.
   4. `connection.execute("PRAGMA foreign_keys = ON")`; verificación `connection.execute("SELECT count(*) FROM sqlite_master").fetchone()`;
      `sqlcipher3.dbapi2.DatabaseError` → cerrar y `EncryptionError("no se pudo abrir la base de datos: clave incorrecta o archivo dañado") from e`.
   5. `connection.executescript(schema)` con `schema = importlib.resources.files("lector_placas.adapters.persistence").joinpath("schema.sql").read_text(encoding="utf-8")`.
   6. Versión: si `schema_version` vacía → `INSERT INTO schema_version(version) VALUES (?)` con 1; si contiene otro valor → cerrar y `RepositoryError("versión de esquema no soportada")`.
   7. `os.chmod(db_path, 0o600)`.
2. Toda escritura dentro de `with self._connection:` (transacción). Cualquier `sqlcipher3.dbapi2.Error` en cualquier
   método → `RepositoryError("<operación> falló") from e` (salvo los casos que el paso 1 convierte en `EncryptionError`).
3. `start_run`: INSERT en `runs` (`status='running'`, `started_at=to_db_time(run.started_at)`, columnas de `run.video`) y
   `log_event(RUN_STARTED, run.started_at, f"run_id={run_id}")` en la misma transacción; devuelve `lastrowid`.
4. `finish_run`: UPDATE de las 7 estadísticas, `finished_at`, `status = 'completed' if succeeded else 'failed'`;
   `rowcount == 0` → `RepositoryError("corrida inexistente")`; `log_event(RUN_FINISHED, finished_at, f"run_id={run_id} status={status}")`.
5. `save_sighting`: INSERT con `ocr_text = plate_text = plate.text`, `reasons = ",".join(r.value ...)`,
   `format_ids = ",".join(...)`, `created_at = to_db_time(...)`, `reviewed_at = NULL`. Si `plate.status is CONFIRMED`:
   `plate_id = _upsert_plate(text, created_at)` y se guarda en la fila. Devuelve `sighting_id`.
   `_upsert_plate(text, at)`: `INSERT INTO plates(plate_text, first_seen_at, last_seen_at) VALUES (?, ?, ?) ON CONFLICT(plate_text) DO UPDATE SET last_seen_at = excluded.last_seen_at`
   y luego `SELECT plate_id FROM plates WHERE plate_text = ?`.
6. `list_sightings(status, limit, offset)`: `1 <= limit <= MAX_PAGE` y `offset >= 0` o `RepositoryError`.
   `SELECT <columnas> FROM sightings WHERE (? IS NULL OR status = ?) ORDER BY sighting_id LIMIT ? OFFSET ?`.
7. `get_sighting`: inexistente → `SightingNotFoundError(f"sighting_id={sighting_id}")`.
8. `record_review(sighting_id, status, corrected_text, reviewed_at)`:
   - `status` ∉ {CONFIRMED, CORRECTED, REJECTED} → `RepositoryError("estado de revisión inválido")`.
   - CORRECTED exige `corrected_text` que cumpla `PLATE_TEXT_REGEX`; los demás exigen `None`; si no → `RepositoryError`.
   - CONFIRMED: `plate_id = _upsert_plate(plate_text_actual, reviewed_at)`; UPDATE `status`, `plate_id`, `reviewed_at`.
   - CORRECTED: `plate_id = _upsert_plate(corrected_text, reviewed_at)`; UPDATE `plate_text`, `status`, `plate_id`, `reviewed_at`.
   - REJECTED: UPDATE `status`, `plate_id = NULL`, `reviewed_at`.
   - Si el avistamiento no existe → `SightingNotFoundError`.
9. `expire_crop_refs(cutoff)` y `delete_records_before(cutoff)`: exactamente la semántica de docs/03-modelo-datos.md §1
   (refs en orden de `sighting_id`; `RecordPurge(sightings_deleted, runs_deleted, plates_deleted, tuple(refs))` usando `rowcount`).
   Consultas: `DELETE FROM runs WHERE started_at < ? AND run_id NOT IN (SELECT run_id FROM sightings)` y
   `DELETE FROM plates WHERE plate_id NOT IN (SELECT plate_id FROM sightings WHERE plate_id IS NOT NULL)`.
10. `log_event`: `len(detail) > 500` → `RepositoryError`; INSERT en `audit_log`.
11. `close()`: idempotente.
12. Conversión fila → `SightingRecord`: `reasons`/`format_ids` vacíos → `()`; si no `tuple(split(","))` (reasons como `UnverifiedReason`);
    fechas con `from_db_time`; `vehicle_type`/`status` con sus enums.

## Casos borde y manejo de errores
- `UNIQUE (run_id, track_id, first_seen_ms)` violado → `RepositoryError`.
- Nunca incluir texto de placa en mensajes de error ni en `audit_log`.

## Tests de aceptación
```python
# tests/integration/test_sqlcipher_repository.py
from __future__ import annotations

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import AuditEvent, RunStart, RunStats, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate, ReviewStatus, Sighting, UnverifiedReason, VehicleType,
)
from lector_placas.domain.errors import EncryptionError, RepositoryError, SightingNotFoundError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 90, 60_000, 30.0, "h264")
CONFIRMED = ConsolidatedPlate("ABC123", 0.97, 1.0, 3, ReviewStatus.CONFIRMED, (),
                              ("co_particular_publico",))
UNVERIFIED = ConsolidatedPlate("XYZ98K", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED,
                               (UnverifiedReason.INSUFFICIENT_READINGS, UnverifiedReason.LOW_CONFIDENCE),
                               ("co_moto",))


def open_repo(tmp_path: Path, key: bytes = bytes(range(32))) -> SqlCipherPlateRepository:
    return SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider(key))


def sighting(run_id: int, track: int, plate: ConsolidatedPlate, at: datetime = T0,
             crop: str | None = "a" * 32) -> Sighting:
    return Sighting(run_id, track, 100, 900, VehicleType.CAR, plate, crop, at)


def test_roundtrip_and_plate_linking(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "calle_lenta", INFO, T0))
    first = repo.save_sighting(sighting(run_id, 1, CONFIRMED))
    second = repo.save_sighting(sighting(run_id, 2, UNVERIFIED, crop=None))
    record = repo.get_sighting(first)
    assert (record.plate_text, record.ocr_text, record.status) == ("ABC123", "ABC123", ReviewStatus.CONFIRMED)
    assert record.created_at == T0
    assert repo.get_sighting(second).reasons == (
        UnverifiedReason.INSUFFICIENT_READINGS, UnverifiedReason.LOW_CONFIDENCE)
    plates = repo._connection.execute("SELECT plate_text FROM plates").fetchall()
    assert plates == [("ABC123",)]
    repo.finish_run(run_id, RunStats(10, 5, 2, 1, 1, 0, 1000, 60_000), T0, True)
    events = [row[0] for row in repo._connection.execute("SELECT event FROM audit_log ORDER BY audit_id")]
    assert events == ["run_started", "run_finished"]
    repo.close()
    repo.close()


def test_file_is_encrypted_and_private(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    repo.save_sighting(sighting(run_id, 1, CONFIRMED))
    repo.close()
    raw = (tmp_path / "lector.db").read_bytes()
    assert not raw.startswith(b"SQLite format 3")
    assert b"ABC123" not in raw
    assert stat.S_IMODE((tmp_path / "lector.db").stat().st_mode) == 0o600


def test_wrong_key_raises(tmp_path: Path) -> None:
    open_repo(tmp_path).close()
    with pytest.raises(EncryptionError):
        open_repo(tmp_path, key=bytes(32))


def test_review_transitions(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    sid = repo.save_sighting(sighting(run_id, 1, UNVERIFIED))
    repo.record_review(sid, ReviewStatus.CORRECTED, "XYZ98L", T0 + timedelta(hours=1))
    record = repo.get_sighting(sid)
    assert (record.plate_text, record.ocr_text, record.status) == ("XYZ98L", "XYZ98K", ReviewStatus.CORRECTED)
    assert record.reviewed_at == T0 + timedelta(hours=1)
    repo.record_review(sid, ReviewStatus.REJECTED, None, T0)
    assert repo.get_sighting(sid).status is ReviewStatus.REJECTED
    with pytest.raises(RepositoryError):
        repo.record_review(sid, ReviewStatus.CORRECTED, None, T0)
    with pytest.raises(RepositoryError):
        repo.record_review(sid, ReviewStatus.CONFIRMED, "ABC123", T0)
    with pytest.raises(RepositoryError):
        repo.record_review(sid, ReviewStatus.UNVERIFIED, None, T0)
    with pytest.raises(SightingNotFoundError):
        repo.record_review(999, ReviewStatus.REJECTED, None, T0)
    repo.close()


def test_list_filters_and_pages(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    ids = [repo.save_sighting(sighting(run_id, i, UNVERIFIED if i % 2 else CONFIRMED))
           for i in range(5)]
    assert [r.sighting_id for r in repo.list_sightings(None, 2, 1)] == ids[1:3]
    assert [r.track_id for r in repo.list_sightings(ReviewStatus.UNVERIFIED, 10, 0)] == [1, 3]
    with pytest.raises(RepositoryError):
        repo.list_sightings(None, 0, 0)
    repo.close()


def test_retention_operations(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    old_run = repo.start_run(RunStart("f" * 64, "p", INFO, T0 - timedelta(days=100)))
    repo.save_sighting(sighting(old_run, 1, CONFIRMED, at=T0 - timedelta(days=100), crop="b" * 32))
    new_run = repo.start_run(RunStart("e" * 64, "p", INFO, T0 - timedelta(days=40)))
    mid = repo.save_sighting(sighting(new_run, 1, UNVERIFIED, at=T0 - timedelta(days=40), crop="c" * 32))
    assert repo.expire_crop_refs(T0 - timedelta(days=30)) == ["b" * 32, "c" * 32]
    assert repo.get_sighting(mid).crop_ref is None
    purge = repo.delete_records_before(T0 - timedelta(days=90))
    assert (purge.sightings_deleted, purge.runs_deleted, purge.plates_deleted) == (1, 1, 1)
    assert purge.crop_refs == ()
    assert [r.sighting_id for r in repo.list_sightings(None, 10, 0)] == [mid]
    repo.close()


def test_constraints_and_audit_limits(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    repo.save_sighting(sighting(run_id, 1, CONFIRMED))
    with pytest.raises(RepositoryError):
        repo.save_sighting(sighting(run_id, 1, CONFIRMED))
    with pytest.raises(RepositoryError):
        repo.log_event(AuditEvent.EXPORT, T0, "x" * 501)
    with pytest.raises(RepositoryError):
        repo.finish_run(999, RunStats(0, 0, 0, 0, 0, 0, 0, None), T0, False)
    repo.close()


def test_unsupported_schema_version(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    with repo._connection:
        repo._connection.execute("UPDATE schema_version SET version = 2")
    repo.close()
    with pytest.raises(RepositoryError):
        open_repo(tmp_path)
```

## Fuera de alcance
Borrado de archivos de recortes (spec 025).

## Definition of Done
- [ ] `schema.sql` idéntico a docs/03-modelo-datos.md §1 e incluido en el paquete (si `importlib.resources` no lo encuentra, detente y reporta).
- [ ] `uv run pytest -m integration tests/integration/test_sqlcipher_repository.py` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `grep -n "execute(f" src/lector_placas/adapters/persistence/sqlcipher_repository.py` muestra solo la línea de `PRAGMA key`.
