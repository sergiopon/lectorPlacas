from __future__ import annotations

import hashlib
import io
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pytest
import yaml

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.adapters.storage.encrypted_crop_store import EncryptedFileCropStore
from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import ConsolidatedPlate, ReviewStatus, Sighting, VehicleType
from lector_placas.domain.errors import (
    ConfigurationError,
    CropStoreError,
    ModelFetchError,
    RepositoryError,
)
from lector_placas.infrastructure.logging_setup import HANDLER_MARK, configure_logging
from lector_placas.infrastructure.model_fetcher import fetch_models
from lector_placas.infrastructure.model_registry import load_manifest
from tests.fixtures.fakes import FakeKeyProvider

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
INFO = VideoInfo(640, 480, 0, 1000, 30.0, "h264")
PLATE = ConsolidatedPlate("ABC123", 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())


def _entry(content: bytes, **extra: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "model_id": "m-uno",
        "filename": "m.onnx",
        "url": "https://github.com/x/m.onnx",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "license": "MIT",
        "source": "test",
    }
    entry.update(extra)
    return entry


def test_manifest_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [_entry(b"a"), _entry(b"b")]}))
    with pytest.raises(ConfigurationError):
        load_manifest(path)


class BrokenStream(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        if self.tell() > 0:
            raise OSError("conexión cortada")
        return super().read(4)


def test_interrupted_download_leaves_no_partial(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [_entry(b"contenido largo")]}))

    def opener(url: str, timeout: float) -> BinaryIO:
        return BrokenStream(b"contenido largo")

    with pytest.raises(ModelFetchError):
        fetch_models(path, tmp_path / "models", opener)
    assert not list((tmp_path / "models").rglob("*.part"))


@pytest.mark.integration
def test_repository_rolls_back_and_cascades(tmp_path: Path) -> None:
    repo = SqlCipherPlateRepository(tmp_path / "db", FakeKeyProvider())
    run_id = repo.start_run(RunStart("a" * 64, "p", INFO, T0))
    repo.save_sighting(Sighting(run_id, 1, 0, 1, VehicleType.CAR, PLATE, None, T0))
    other = ConsolidatedPlate("XYZ987", 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())
    with pytest.raises(RepositoryError):
        repo.save_sighting(Sighting(run_id, 1, 0, 1, VehicleType.CAR, other, None, T0))
    plates = [r[0] for r in repo._connection.execute("SELECT plate_text FROM plates")]
    assert plates == ["ABC123"]
    assert repo.list_sightings(None, 10, 50) == []
    with repo._connection:
        repo._connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
    assert repo.list_sightings(None, 10, 0) == []
    repo.close()


@pytest.mark.integration
def test_crop_store_sweeps_orphan_tmp_and_rejects_uppercase(tmp_path: Path) -> None:
    store = EncryptedFileCropStore(tmp_path / "crops", FakeKeyProvider())
    ref = store.save(np.zeros((4, 4, 3), np.uint8))
    orphan = tmp_path / "crops" / ref[:2] / "huerfano.tmp"
    orphan.write_bytes(b"x")
    past = (datetime.now(UTC) - timedelta(days=40)).timestamp()
    os.utime(orphan, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=30)) == 1
    assert not orphan.exists()
    with pytest.raises(CropStoreError):
        store.load(ref.upper())


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARK, False):
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_logging_redacts_args_and_multiple_plates(tmp_path: Path, restore_logging: None) -> None:
    log_file = tmp_path / "logs" / "lector.log"
    configure_logging("INFO", log_file)
    logger = logging.getLogger("lector_placas.review")
    logger.info("placas %s y %s", "ABC123", "XYZ98K")
    logger.info("lista ABC123,DEF456;123ABC")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    for plate in ("ABC123", "XYZ98K", "DEF456", "123ABC"):
        assert plate not in content
