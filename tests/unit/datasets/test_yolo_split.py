from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.datasets.yolo_split import iter_split
from lector_placas.domain.errors import DatasetError


def make_dataset(root: Path) -> Path:
    (root / "images" / "val").mkdir(parents=True)
    (root / "labels" / "val").mkdir(parents=True)
    cv2.imwrite(str(root / "images" / "val" / "b.png"), np.zeros((100, 200, 3), np.uint8))
    cv2.imwrite(str(root / "images" / "val" / "a.jpg"), np.zeros((50, 50, 3), np.uint8))
    (root / "images" / "val" / "notas.txt").write_text("x", encoding="utf-8")
    (root / "labels" / "val" / "b.txt").write_text("0 0.5 0.5 0.5 0.2\n", encoding="utf-8")
    return root


def test_iter_split_reads_boxes_in_pixels(tmp_path: Path) -> None:
    items = list(iter_split(make_dataset(tmp_path), "val"))
    assert [item.name for item in items] == ["a.jpg", "b.png"]
    assert items[0].boxes == ()
    box = items[1].boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx((50, 40, 150, 60))
    assert items[1].image.shape == (100, 200, 3)


def test_iter_split_errors(tmp_path: Path) -> None:
    with pytest.raises(DatasetError):
        list(iter_split(tmp_path, "val"))
    with pytest.raises(DatasetError):
        list(iter_split(make_dataset(tmp_path), "test"))
