"""Tests de integración para el esquema v3 de SQLCipher."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    CropQuality,
    ReviewStatus,
    Sighting,
    SightingRecord,
    VehicleType,
)
from lector_placas.domain.errors import RepositoryError
from lector_placas.infrastructure.paths import ensure_private_dir
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration


def test_new_database_is_current_version(tmp_path: Path) -> None:
    """Una BD nueva tiene el esquema vigente con las columnas de calidad y de ubicación."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(db_path, key_provider)
    repo.close()

    # Usar la misma clave para abrir la conexión cruda
    from lector_placas.infrastructure.crypto import KeyPurpose, derive_key

    key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()
    connection = sqlcipher.connect(str(db_path))
    connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 4

    # Verificar que las columnas existen
    pragma = connection.execute("PRAGMA table_info(sightings)").fetchall()
    column_names = [row[1] for row in pragma]
    assert "plate_width_px" in column_names
    assert "plate_height_px" in column_names
    assert "sharpness" in column_names
    assert "contrast" in column_names
    assert "duplicate_of" in column_names
    connection.close()


def _verify_quality_in_list_sightings(
    records: list[SightingRecord], quality1: CropQuality
) -> tuple[SightingRecord, SightingRecord]:
    """Verifica la calidad en list_sightings y retorna los dos registros."""
    assert len(records) == 2
    r1 = next(r for r in records if r.track_id == 0)
    r2 = next(r for r in records if r.track_id == 1)
    assert r1.quality == quality1
    assert r2.quality is None
    assert r1.duplicate_of is None
    assert r2.duplicate_of is None
    return r1, r2


def _verify_quality_in_get_sighting(
    repo: SqlCipherPlateRepository, r1: SightingRecord, r2: SightingRecord, quality1: CropQuality
) -> None:
    """Verifica la calidad en get_sighting."""
    assert repo.get_sighting(r1.sighting_id).quality == quality1
    assert repo.get_sighting(r2.sighting_id).quality is None


def _verify_quality_in_browser(repo: SqlCipherPlateRepository, quality1: CropQuality) -> None:
    """Verifica la calidad en el navegador."""
    browser_records = repo.browser().search_sightings(
        __import__("lector_placas.application.ports", fromlist=["SightingQuery"]).SightingQuery(),
        10,
        0,
    )
    assert len(browser_records) == 2
    br1 = next(r for r in browser_records if r.track_id == 0)
    br2 = next(r for r in browser_records if r.track_id == 1)
    assert br1.quality == quality1
    assert br2.quality is None


def test_quality_roundtrip(tmp_path: Path) -> None:
    """La calidad se guarda y se lee correctamente."""
    db_path = tmp_path / "test.db"
    repo = SqlCipherPlateRepository(db_path, FakeKeyProvider())

    # Crear una corrida
    run_id = _create_run(repo, "v1.mp4", 1920, 1080)

    # Guardar dos avistamientos: uno con calidad, otro sin
    quality1 = CropQuality(100, 30, 12.5, 40.0)
    sighting1 = Sighting(
        run_id,
        0,
        0,
        1000,
        VehicleType.CAR,
        ConsolidatedPlate("ABC123", 0.9, 0.8, 1, ReviewStatus.CONFIRMED, (), ()),
        "a" * 32,
        datetime.now(UTC),
        quality1,
    )
    repo.save_sighting(sighting1)

    sighting2 = Sighting(
        run_id,
        1,
        1000,
        2000,
        VehicleType.CAR,
        ConsolidatedPlate("DEF456", 0.8, 0.7, 1, ReviewStatus.CONFIRMED, (), ()),
        "b" * 32,
        datetime.now(UTC),
        None,
    )
    repo.save_sighting(sighting2)

    # Leer con list_sightings
    records = repo.list_sightings(None, 10, 0)
    r1, r2 = _verify_quality_in_list_sightings(records, quality1)

    # Leer con get_sighting
    _verify_quality_in_get_sighting(repo, r1, r2, quality1)

    # Leer con navegador
    _verify_quality_in_browser(repo, quality1)

    repo.close()


def test_v2_database_is_migrated_to_current(tmp_path: Path) -> None:
    """Una BD v2 se migra al esquema vigente automáticamente."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()

    # Crear BD con esquema v2
    _create_v2_db(db_path, key_provider)

    # Abrir con el repositorio: debe migrar
    repo = SqlCipherPlateRepository(db_path, key_provider)
    repo.close()

    # Verificar versión
    connection = _raw_connect(db_path, key_provider)
    version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 4
    connection.close()


def test_failed_v3_migration_leaves_v2_intact(tmp_path: Path) -> None:
    """Si la migración v2→v3 falla, la BD queda en v2."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()

    # Crear BD con esquema v2
    _create_v2_db(db_path, key_provider)

    # Sabotear la migración creando una tabla que causará conflicto
    connection = _raw_connect(db_path, key_provider)
    connection.execute("CREATE TABLE sightings_v3 (x INTEGER)")
    connection.close()

    # Intentar abrir debe fallar
    with pytest.raises(RepositoryError):
        SqlCipherPlateRepository(db_path, key_provider)

    # Verificar que la BD sigue siendo v2
    connection = _raw_connect(db_path, key_provider)
    version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 2
    connection.close()


def test_duplicate_of_set_null_on_delete(tmp_path: Path) -> None:
    """Borrar un avistamiento pone NULL en duplicate_of de quien apuntaba a él."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(db_path, key_provider)

    # Crear una corrida y dos avistamientos
    run_id = _create_run(repo, "v1.mp4", 1920, 1080)
    sighting1 = Sighting(
        run_id,
        0,
        0,
        1000,
        VehicleType.CAR,
        ConsolidatedPlate("ABC123", 0.9, 0.8, 1, ReviewStatus.CONFIRMED, (), ()),
        None,
        datetime.now(UTC),
    )
    id1 = repo.save_sighting(sighting1)

    sighting2 = Sighting(
        run_id,
        1,
        1000,
        2000,
        VehicleType.CAR,
        ConsolidatedPlate("ABC123", 0.9, 0.8, 1, ReviewStatus.CONFIRMED, (), ()),
        None,
        datetime.now(UTC),
    )
    id2 = repo.save_sighting(sighting2)

    repo.close()

    # Con una conexión cruda, poner duplicate_of y borrar
    connection = _raw_connect(db_path, key_provider)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("UPDATE sightings SET duplicate_of = ? WHERE sighting_id = ?", (id1, id2))
    connection.execute("DELETE FROM sightings WHERE sighting_id = ?", (id1,))
    connection.commit()

    # Verificar que el otro quedó con NULL
    result = connection.execute(
        "SELECT duplicate_of FROM sightings WHERE sighting_id = ?", (id2,)
    ).fetchone()
    assert result[0] is None
    connection.close()


def test_partial_quality_is_rejected(tmp_path: Path) -> None:
    """No se puede guardar calidad parcial (CHECK constraint)."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(db_path, key_provider)
    run_id = _create_run(repo, "v1.mp4", 1920, 1080)
    repo.close()

    # Con una conexión cruda, intentar guardar calidad parcial
    connection = _raw_connect(db_path, key_provider)
    with pytest.raises(sqlcipher.IntegrityError):
        connection.execute(
            """
            INSERT INTO sightings (
                run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, ocr_text,
                plate_text, confidence, agreement, num_readings, status, reasons, format_ids,
                created_at, reviewed_at, plate_width_px
            ) VALUES (?, 0, 0, 1000, 'car', 'ABC123', 'ABC123', 0.9, 0.8, 1, 'confirmed',
                     '', '', '2026-01-01T00:00:00', NULL, 10)
            """,
            (run_id,),
        )
        connection.commit()
    connection.close()


def test_run_frame_sizes(tmp_path: Path) -> None:
    """run_frame_sizes devuelve los tamaños de cada corrida."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(db_path, key_provider)

    run_id1 = _create_run(repo, "v1.mp4", 1920, 1080)
    run_id2 = _create_run(repo, "v2.mp4", 1280, 720)

    sizes = repo.run_frame_sizes()
    assert sizes == {run_id1: (1920, 1080), run_id2: (1280, 720)}

    repo.close()


def _create_run(repo: SqlCipherPlateRepository, video_name: str, width: int, height: int) -> int:
    """Crea una corrida de prueba."""
    from lector_placas.application.ports import RunStart, VideoInfo

    video = VideoInfo(width, height, 0, 1000, 10.0, "mpeg4")
    run_start = RunStart("a" * 64, "test", video, datetime.now(UTC))
    return repo.start_run(run_start)


def _raw_connect(db_path: Path, key_provider: FakeKeyProvider) -> sqlcipher.Connection:
    """Abre una conexión cruda a la base de datos cifrada, sin pasar por el repositorio."""
    from lector_placas.infrastructure.crypto import KeyPurpose, derive_key

    key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()
    conn = sqlcipher.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    return conn


def _create_v2_db(db_path: Path, key_provider: FakeKeyProvider | None = None) -> None:
    """Crea una BD en esquema v2 (sin las columnas del esquema v3)."""
    from lector_placas.infrastructure.crypto import KeyPurpose, derive_key

    if key_provider is None:
        key_provider = FakeKeyProvider()
    ensure_private_dir(db_path.parent)
    connection = sqlcipher.connect(str(db_path))
    key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()
    connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")

    # Crear esquema v2 (sin las 5 columnas nuevas)
    connection.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_version(version) VALUES (2)")
    connection.execute(
        """
        CREATE TABLE runs (
            run_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            video_sha256           TEXT    NOT NULL CHECK (length(video_sha256) = 64),
            profile                TEXT    NOT NULL CHECK (length(profile) BETWEEN 1 AND 64),
            width                  INTEGER NOT NULL CHECK (width > 0),
            height                 INTEGER NOT NULL CHECK (height > 0),
            rotation_deg           INTEGER NOT NULL CHECK (rotation_deg IN (0, 90, 180, 270)),
            duration_ms            INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
            started_at             TEXT    NOT NULL,
            finished_at            TEXT,
            status                 TEXT    NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            frames_decoded         INTEGER CHECK (frames_decoded IS NULL OR frames_decoded >= 0),
            frames_processed       INTEGER CHECK (frames_processed IS NULL OR frames_processed >= 0),
            tracks_total           INTEGER CHECK (tracks_total IS NULL OR tracks_total >= 0),
            sightings_confirmed    INTEGER CHECK (sightings_confirmed IS NULL OR sightings_confirmed >= 0),
            sightings_unverified   INTEGER CHECK (sightings_unverified IS NULL OR sightings_unverified >= 0),
            tracks_without_reading INTEGER CHECK (tracks_without_reading IS NULL OR tracks_without_reading >= 0),
            processing_ms          INTEGER CHECK (processing_ms IS NULL OR processing_ms >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE plates (
            plate_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_text    TEXT NOT NULL UNIQUE,
            first_seen_at TEXT NOT NULL,
            last_seen_at  TEXT NOT NULL
        )
        """
    )
    # Tabla v2 SIN las columnas nuevas
    connection.execute(
        """
        CREATE TABLE sightings (
            sighting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            plate_id      INTEGER REFERENCES plates(plate_id) ON DELETE SET NULL,
            track_id      INTEGER NOT NULL CHECK (track_id >= 0),
            first_seen_ms INTEGER NOT NULL CHECK (first_seen_ms >= 0),
            last_seen_ms  INTEGER NOT NULL CHECK (last_seen_ms >= first_seen_ms),
            vehicle_type  TEXT    NOT NULL CHECK (vehicle_type IN ('car', 'motorcycle', 'bus', 'truck')),
            ocr_text      TEXT    NOT NULL CHECK (length(ocr_text) BETWEEN 1 AND 10),
            plate_text    TEXT    NOT NULL CHECK (length(plate_text) BETWEEN 1 AND 10),
            confidence    REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
            agreement     REAL    NOT NULL CHECK (agreement BETWEEN 0.0 AND 1.0),
            num_readings  INTEGER NOT NULL CHECK (num_readings >= 1),
            status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified', 'rejected', 'corrected', 'illegible')),
            reasons       TEXT    NOT NULL,
            format_ids    TEXT    NOT NULL,
            crop_ref      TEXT,
            created_at    TEXT    NOT NULL,
            reviewed_at   TEXT,
            UNIQUE (run_id, track_id, first_seen_ms)
        )
        """
    )
    connection.commit()
    connection.close()
