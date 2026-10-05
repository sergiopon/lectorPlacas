"""Tests de integración para el esquema v4 de SQLCipher (ubicación de la placa)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    CropQuality,
    PlateLocation,
    ReviewStatus,
    Sighting,
    VehicleType,
)
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration


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


def _sighting(
    run_id: int,
    track_id: int,
    text: str,
    quality: CropQuality | None,
    location: PlateLocation | None,
) -> Sighting:
    """Construye un avistamiento de prueba."""
    return Sighting(
        run_id,
        track_id,
        track_id * 1000,
        track_id * 1000 + 1000,
        VehicleType.CAR,
        ConsolidatedPlate(text, 0.9, 0.8, 1, ReviewStatus.CONFIRMED, (), ()),
        "a" * 32,
        datetime.now(UTC),
        quality,
        location,
    )


def _downgrade_to_v3(db_path: Path, key_provider: FakeKeyProvider) -> None:
    """Quita las columnas de ubicación y marca la BD como v3."""
    connection = _raw_connect(db_path, key_provider)
    for name in ("frame_ms", "box_x", "box_y", "box_w", "box_h"):
        connection.execute(f"ALTER TABLE sightings DROP COLUMN {name}")
    connection.execute("UPDATE schema_version SET version = 3")
    connection.commit()
    connection.close()


def _assert_new_location_roundtrip(repo: SqlCipherPlateRepository, run_id: int) -> None:
    """Guarda un avistamiento con ubicación y lo lee igual."""
    new_location = PlateLocation(10, 1, 2, 3, 4)
    repo.save_sighting(_sighting(run_id, 1, "DEF456", None, new_location))
    again = repo.list_sightings(None, 10, 0)
    assert next(r for r in again if r.track_id == 1).location == new_location


def test_location_roundtrip(tmp_path: Path) -> None:
    """La ubicación se guarda y se lee con list_sightings, get_sighting y el navegador."""
    repo = SqlCipherPlateRepository(tmp_path / "test.db", FakeKeyProvider())
    run_id = _create_run(repo, "v1.mp4", 1920, 1080)
    location = PlateLocation(1500, 130, 185, 100, 30)
    repo.save_sighting(_sighting(run_id, 0, "ABC123", None, location))
    repo.save_sighting(_sighting(run_id, 1, "DEF456", None, None))

    records = repo.list_sightings(None, 10, 0)
    browser_records = repo.browser().search_sightings(SightingQuery(), 10, 0)
    for group in (records, browser_records):
        assert len(group) == 2
        assert next(r for r in group if r.track_id == 0).location == location
        assert next(r for r in group if r.track_id == 1).location is None
    for record in records:
        expected = location if record.track_id == 0 else None
        assert repo.get_sighting(record.sighting_id).location == expected
    repo.close()


def test_v3_database_is_migrated_to_v4(tmp_path: Path) -> None:
    """Una BD v3 se migra a v4 conservando las filas, con la ubicación en NULL."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    repo = SqlCipherPlateRepository(db_path, key_provider)
    run_id = _create_run(repo, "v1.mp4", 1920, 1080)
    quality = CropQuality(100, 30, 12.5, 40.0)
    repo.save_sighting(_sighting(run_id, 0, "ABC123", quality, None))
    repo.close()

    _downgrade_to_v3(db_path, key_provider)

    repo = SqlCipherPlateRepository(db_path, key_provider)
    version = repo._connection.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 4
    records = repo.list_sightings(None, 10, 0)
    assert len(records) == 1
    assert records[0].quality == quality
    assert records[0].location is None

    _assert_new_location_roundtrip(repo, run_id)
    repo.close()


def test_location_columns_in_new_database(tmp_path: Path) -> None:
    """Una BD nueva tiene las cinco columnas de ubicación al final de `sightings`."""
    db_path = tmp_path / "test.db"
    key_provider = FakeKeyProvider()
    SqlCipherPlateRepository(db_path, key_provider).close()
    connection = _raw_connect(db_path, key_provider)
    rows = connection.execute("PRAGMA table_info(sightings)").fetchall()
    connection.close()
    last = rows[-5:]
    assert [row[1] for row in last] == ["frame_ms", "box_x", "box_y", "box_w", "box_h"]
    assert all(row[2] == "INTEGER" and row[3] == 0 for row in last)
