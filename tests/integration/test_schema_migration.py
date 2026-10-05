"""Migración del esquema de `sightings` de v1 a v2."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import RepositoryError
from lector_placas.infrastructure.crypto import KeyPurpose, derive_key
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, 60_000, 30.0, "h264")
CONFIRMED = ConsolidatedPlate(
    "ABC123", 0.97, 1.0, 3, ReviewStatus.CONFIRMED, (), ("co_particular_publico",)
)
UNVERIFIED = ConsolidatedPlate(
    "XYZ98K",
    0.5,
    0.5,
    2,
    ReviewStatus.UNVERIFIED,
    (UnverifiedReason.INSUFFICIENT_READINGS,),
    ("co_moto",),
)

# Lista de columnas fija (no se interpola: evita el falso positivo de S608).
_INSERT_SIGHTINGS_V1 = """
INSERT INTO sightings_v1 (
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
)
SELECT
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
FROM sightings
"""


def _sighting(run_id: int, track: int, plate: ConsolidatedPlate, crop: str = "a" * 32) -> Sighting:
    return Sighting(run_id, track, 100, 900, VehicleType.CAR, plate, crop, T0)


def _downgrade_to_v1(repo: SqlCipherPlateRepository) -> None:
    """Recrea `sightings` con el `CHECK` de v1 (sin `'illegible'`) y pone `schema_version` a 1."""
    conn = repo._connection
    original_isolation_level = conn.isolation_level
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        CREATE TABLE sightings_v1 (
            sighting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            plate_id      INTEGER REFERENCES plates(plate_id) ON DELETE SET NULL,
            track_id      INTEGER NOT NULL CHECK (track_id >= 0),
            first_seen_ms INTEGER NOT NULL CHECK (first_seen_ms >= 0),
            last_seen_ms  INTEGER NOT NULL CHECK (last_seen_ms >= first_seen_ms),
            vehicle_type  TEXT    NOT NULL CHECK (vehicle_type IN ('car', 'motorcycle', 'bus',
                                                                   'truck')),
            ocr_text      TEXT    NOT NULL CHECK (length(ocr_text) BETWEEN 1 AND 10
                                                  AND ocr_text NOT GLOB '*[^A-Z0-9]*'),
            plate_text    TEXT    NOT NULL CHECK (length(plate_text) BETWEEN 1 AND 10
                                                  AND plate_text NOT GLOB '*[^A-Z0-9]*'),
            confidence    REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
            agreement     REAL    NOT NULL CHECK (agreement BETWEEN 0.0 AND 1.0),
            num_readings  INTEGER NOT NULL CHECK (num_readings >= 1),
            status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified',
                                                              'rejected', 'corrected')),
            reasons       TEXT    NOT NULL,
            format_ids    TEXT    NOT NULL,
            crop_ref      TEXT CHECK (crop_ref IS NULL OR (length(crop_ref) = 32
                                                           AND crop_ref NOT GLOB '*[^0-9a-f]*')),
            created_at    TEXT    NOT NULL,
            reviewed_at   TEXT,
            UNIQUE (run_id, track_id, first_seen_ms)
        )
        """
    )
    conn.execute(_INSERT_SIGHTINGS_V1)
    conn.execute("DROP TABLE sightings")
    conn.execute("ALTER TABLE sightings_v1 RENAME TO sightings")
    conn.execute("CREATE INDEX idx_sightings_status ON sightings(status)")
    conn.execute("CREATE INDEX idx_sightings_created_at ON sightings(created_at)")
    conn.execute("CREATE INDEX idx_sightings_plate_id ON sightings(plate_id)")
    conn.execute(
        "CREATE INDEX idx_sightings_crop_ref ON sightings(crop_ref) WHERE crop_ref IS NOT NULL"
    )
    conn.execute("UPDATE schema_version SET version = 1")
    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.isolation_level = original_isolation_level


def _raw_connect(db_path: Path, key_provider: FakeKeyProvider) -> sqlcipher.Connection:
    """Abre una conexión cruda a la base de datos cifrada, sin pasar por el repositorio."""
    key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()
    conn = sqlcipher.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    return conn


def _build_v1_database(tmp_path: Path, key_provider: FakeKeyProvider) -> list[SightingRecord]:
    """Crea una BD v1 con avistamientos de los cuatro estados y devuelve sus registros."""
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    repo.save_sighting(_sighting(run_id, 0, UNVERIFIED, crop="a" * 32))
    repo.save_sighting(_sighting(run_id, 1, CONFIRMED, crop="b" * 32))
    corrected_id = repo.save_sighting(_sighting(run_id, 2, UNVERIFIED, crop="c" * 32))
    repo.record_review(corrected_id, ReviewStatus.CORRECTED, "XYZ98L", T0 + timedelta(hours=1))
    rejected_id = repo.save_sighting(_sighting(run_id, 3, UNVERIFIED, crop="d" * 32))
    repo.record_review(rejected_id, ReviewStatus.REJECTED, None, T0 + timedelta(hours=2))
    records = repo.list_sightings(None, 10, 0)
    _downgrade_to_v1(repo)
    repo.close()
    return records


def test_v1_database_is_migrated_preserving_rows(tmp_path: Path) -> None:
    key_provider = FakeKeyProvider()
    records_before = _build_v1_database(tmp_path, key_provider)
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    version = repo._connection.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 3
    records_after = repo.list_sightings(None, 10, 0)
    assert records_after == records_before
    repo.close()


def test_migrated_database_accepts_illegible(tmp_path: Path) -> None:
    key_provider = FakeKeyProvider()
    records_before = _build_v1_database(tmp_path, key_provider)
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    target = records_before[0]
    repo.record_review(target.sighting_id, ReviewStatus.ILLEGIBLE, None, T0 + timedelta(hours=3))
    updated = repo.get_sighting(target.sighting_id)
    assert updated.status is ReviewStatus.ILLEGIBLE
    assert updated.plate_text == target.plate_text
    assert updated.ocr_text == target.ocr_text
    repo.close()


def test_migration_keeps_indexes_and_autoincrement(tmp_path: Path) -> None:
    key_provider = FakeKeyProvider()
    records_before = _build_v1_database(tmp_path, key_provider)
    max_id_before = max(record.sighting_id for record in records_before)
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    index_names = {
        row[0]
        for row in repo._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'sightings'"
        ).fetchall()
        if not row[0].startswith("sqlite_autoindex_")
    }
    assert index_names == {
        "idx_sightings_status",
        "idx_sightings_created_at",
        "idx_sightings_plate_id",
        "idx_sightings_crop_ref",
        "idx_sightings_duplicate_of",
    }
    run_id = repo.start_run(RunStart("e" * 64, "p", INFO, T0))
    new_id = repo.save_sighting(_sighting(run_id, 9, CONFIRMED, crop="e" * 32))
    assert new_id > max_id_before
    repo.close()


def test_reopening_migrated_database_does_not_migrate_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key_provider = FakeKeyProvider()
    records_before = _build_v1_database(tmp_path, key_provider)
    first = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    first.close()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        second = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    assert "esquema migrado" not in caplog.text
    assert second.list_sightings(None, 10, 0) == records_before
    second.close()


def test_failed_migration_leaves_v1_intact(tmp_path: Path) -> None:
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    run_id = repo.start_run(RunStart("f" * 64, "p", INFO, T0))
    sighting_id = repo.save_sighting(_sighting(run_id, 0, UNVERIFIED))
    _downgrade_to_v1(repo)
    repo._connection.execute("CREATE TABLE sightings_v2 (x INTEGER)")
    repo._connection.commit()
    repo.close()

    with pytest.raises(RepositoryError):
        SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)

    raw = _raw_connect(tmp_path / "lector.db", key_provider)
    version = raw.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 1
    rows = raw.execute("SELECT sighting_id, status FROM sightings").fetchall()
    assert rows == [(sighting_id, "unverified")]
    raw.close()


class _LockingConnection:
    """Envuelve una conexión SQLCipher real simulando que `BEGIN IMMEDIATE` está bloqueada.

    `sqlcipher3.dbapi2.Connection` es un tipo inmutable: no admite parchear `execute` ni en la
    clase ni en la instancia. Se envuelve el resultado de `sqlcipher.connect` para simular, de
    forma rápida y determinista, el `sqlcipher.OperationalError("database is locked")` que
    lanzaría un `BEGIN IMMEDIATE` real contra una base de datos bloqueada por otra conexión.
    """

    def __init__(self, real: sqlcipher.Connection) -> None:
        object.__setattr__(self, "_real", real)

    def execute(self, sql: str, *args: object) -> object:
        if sql == "BEGIN IMMEDIATE":
            raise sqlcipher.OperationalError("database is locked")
        return self._real.execute(sql, *args)

    def executescript(self, script: str) -> object:
        return self._real.executescript(script)

    def close(self) -> None:
        self._real.close()

    def __enter__(self) -> object:
        return self._real.__enter__()

    def __exit__(self, *exc_info: object) -> bool | None:
        return self._real.__exit__(*exc_info)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._real, name, value)


def test_locked_database_raises_repository_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_provider = FakeKeyProvider()
    records_before = _build_v1_database(tmp_path, key_provider)

    # Otra conexión mantiene un BEGIN IMMEDIATE abierto: la BD queda realmente bloqueada.
    blocker = _raw_connect(tmp_path / "lector.db", key_provider)
    blocker.isolation_level = None
    blocker.execute("BEGIN IMMEDIATE")

    real_connect = sqlcipher.connect

    def locking_connect(path: str) -> _LockingConnection:
        return _LockingConnection(real_connect(path))

    # El timeout real de `sqlite3.connect` (5 s) haría el fallo lento pero no distinto: se
    # simula con la conexión anterior para que sea rápido y determinista.
    monkeypatch.setattr(sqlcipher, "connect", locking_connect)
    with pytest.raises(RepositoryError):
        SqlCipherPlateRepository(tmp_path / "lector.db", key_provider)
    monkeypatch.undo()

    blocker.execute("ROLLBACK")
    blocker.close()

    raw = _raw_connect(tmp_path / "lector.db", key_provider)
    version = raw.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 1
    rows = raw.execute("SELECT sighting_id, status FROM sightings ORDER BY sighting_id").fetchall()
    assert rows == [(record.sighting_id, record.status.value) for record in records_before]
    raw.close()
