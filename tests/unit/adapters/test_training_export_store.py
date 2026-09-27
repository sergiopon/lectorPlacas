from __future__ import annotations

import csv
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.adapters.export.training_export_store import FilesystemTrainingExportStore
from lector_placas.domain.errors import ExportError

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def image() -> np.ndarray:
    img = np.zeros((10, 30, 3), np.uint8)
    img[:, :, 2] = 200
    return img


def test_write_samples_creates_private_dataset(tmp_path: Path) -> None:
    store = FilesystemTrainingExportStore(tmp_path / "own")
    path = store.write_samples([("ABC123", image()), ("XYZ98K", image())], T0)
    assert path.name == "reviewed-20260926T120000Z"
    rows = list(csv.DictReader((path / "annotations.csv").open(encoding="utf-8")))
    assert rows == [
        {"image_path": "images/000000.png", "plate_text": "ABC123"},
        {"image_path": "images/000001.png", "plate_text": "XYZ98K"},
    ]
    np.testing.assert_array_equal(cv2.imread(str(path / "images" / "000000.png")), image())
    for file in (path / "annotations.csv", path / "images" / "000001.png"):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    for directory in (tmp_path / "own", path, path / "images"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    with pytest.raises(ExportError):
        store.write_samples([], T0)


def test_rejects_invalid_plate_text(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        FilesystemTrainingExportStore(tmp_path / "own").write_samples([("abc", image())], T0)


def test_delete_older_than(tmp_path: Path) -> None:
    store = FilesystemTrainingExportStore(tmp_path / "own")
    assert store.delete_older_than(T0) == 0
    old = store.write_samples([("ABC123", image())], T0)
    new = store.write_samples([("ABC123", image())], T0 + timedelta(seconds=1))
    past = (datetime.now(UTC) - timedelta(days=200)).timestamp()
    os.utime(old, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=180)) == 1
    assert not old.exists() and new.exists()
