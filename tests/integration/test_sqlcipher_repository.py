from __future__ import annotations

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import AuditEvent, RunStart, RunStats, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import EncryptionError, RepositoryError, SightingNotFoundError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 90, 60_000, 30.0, "h264")
CONFIRMED = ConsolidatedPlate(
    "ABC123", 0.97, 1.0, 3, ReviewStatus.CONFIRMED, (), ("co_particular_publico",)
)
UNVERIFIED = ConsolidatedPlate(
    "XYZ98K",
    0.5,
    0.5,
    2,
    ReviewStatus.UNVERIFIED,
    (UnverifiedReason.INSUFFICIENT_READINGS, UnverifiedReason.LOW_CONFIDENCE),
    ("co_moto",),
)


def open_repo(tmp_path: Path, key: bytes = bytes(range(32))) -> SqlCipherPlateRepository:
    return SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider(key))


def sighting(
    run_id: int,
    track: int,
    plate: ConsolidatedPlate,
    at: datetime = T0,
    crop: str | None = "a" * 32,
) -> Sighting:
    return Sighting(run_id, track, 100, 900, VehicleType.CAR, plate, crop, at)


def test_roundtrip_and_plate_linking(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    run_id = repo.start_run(RunStart("f" * 64, "calle_lenta", INFO, T0))
    first = repo.save_sighting(sighting(run_id, 1, CONFIRMED))
    second = repo.save_sighting(sighting(run_id, 2, UNVERIFIED, crop=None))
    record = repo.get_sighting(first)
    assert (record.plate_text, record.ocr_text, record.status) == (
        "ABC123",
        "ABC123",
        ReviewStatus.CONFIRMED,
    )
    assert record.created_at == T0
    assert repo.get_sighting(second).reasons == (
        UnverifiedReason.INSUFFICIENT_READINGS,
        UnverifiedReason.LOW_CONFIDENCE,
    )
    plates = repo._connection.execute("SELECT plate_text FROM plates").fetchall()
    assert plates == [("ABC123",)]
    repo.finish_run(run_id, RunStats(10, 5, 2, 1, 1, 0, 1000, 60_000), T0, True)
    events = [
        row[0] for row in repo._connection.execute("SELECT event FROM audit_log ORDER BY audit_id")
    ]
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
    assert (record.plate_text, record.ocr_text, record.status) == (
        "XYZ98L",
        "XYZ98K",
        ReviewStatus.CORRECTED,
    )
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
    ids = [
        repo.save_sighting(sighting(run_id, i, UNVERIFIED if i % 2 else CONFIRMED))
        for i in range(5)
    ]
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
    mid = repo.save_sighting(
        sighting(new_run, 1, UNVERIFIED, at=T0 - timedelta(days=40), crop="c" * 32)
    )
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
