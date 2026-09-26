from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.storage.encrypted_crop_store import EncryptedFileCropStore
from lector_placas.domain.errors import CropNotFoundError, CropStoreError, EncryptionError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration


def image() -> np.ndarray:
    rng = np.random.default_rng(1)
    return rng.integers(0, 255, (30, 100, 3), dtype=np.uint8)


def store(tmp_path: Path, key: bytes = bytes(range(32))) -> EncryptedFileCropStore:
    return EncryptedFileCropStore(tmp_path / "crops", FakeKeyProvider(key))


def test_roundtrip_is_lossless_and_encrypted(tmp_path: Path) -> None:
    crops = store(tmp_path)
    ref = crops.save(image())
    np.testing.assert_array_equal(crops.load(ref), image())
    path = tmp_path / "crops" / ref[:2] / f"{ref}.bin"
    assert b"\x89PNG" not in path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "crops").stat().st_mode) == 0o700
    assert not list((tmp_path / "crops").rglob("*.tmp"))


def test_refs_are_random(tmp_path: Path) -> None:
    crops = store(tmp_path)
    assert crops.save(image()) != crops.save(image())


def test_wrong_key_and_tamper(tmp_path: Path) -> None:
    ref = store(tmp_path).save(image())
    with pytest.raises(EncryptionError):
        store(tmp_path, key=bytes(32)).load(ref)
    path = tmp_path / "crops" / ref[:2] / f"{ref}.bin"
    data = bytearray(path.read_bytes())
    data[20] ^= 1
    path.write_bytes(bytes(data))
    with pytest.raises(EncryptionError):
        store(tmp_path).load(ref)


def test_delete_and_missing(tmp_path: Path) -> None:
    crops = store(tmp_path)
    ref = crops.save(image())
    crops.delete(ref)
    crops.delete(ref)
    with pytest.raises(CropNotFoundError):
        crops.load(ref)
    with pytest.raises(CropStoreError):
        crops.load("../etc/passwd")
    with pytest.raises(CropStoreError):
        crops.save(np.zeros((0, 3, 3), np.uint8))


def test_delete_older_than(tmp_path: Path) -> None:
    crops = store(tmp_path)
    old_ref = crops.save(image())
    new_ref = crops.save(image())
    old_path = tmp_path / "crops" / old_ref[:2] / f"{old_ref}.bin"
    past = (datetime.now(UTC) - timedelta(days=40)).timestamp()
    os.utime(old_path, (past, past))
    assert crops.delete_older_than(datetime.now(UTC) - timedelta(days=30)) == 1
    assert not old_path.exists()
    np.testing.assert_array_equal(crops.load(new_ref), image())
