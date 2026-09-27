from __future__ import annotations

import csv
from pathlib import Path

import pytest

from lector_placas.datasets.chars_to_ocr import chars_to_ocr, plate_text_from_boxes
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError
from tests.fixtures.plate_catalog import build_test_catalog
from tests.unit.datasets.synthetic import make_source, noise

NAMES = ["A", "B", "c", "1", "2", "3", "placa", "ciudad"]
PLATE = "6 0.5 0.5 0.8 0.6"
CHARS = [
    "3 0.55 0.45 0.08 0.3",
    "0 0.20 0.45 0.08 0.3",
    "5 0.75 0.45 0.08 0.3",
    "2 0.40 0.45 0.08 0.3",
    "1 0.30 0.45 0.08 0.3",
    "4 0.65 0.45 0.08 0.3",
    "7 0.50 0.72 0.60 0.08",
]


def test_plate_text_from_boxes() -> None:
    plate = BoundingBox(0, 0, 100, 40)
    chars = [
        (BoundingBox(50, 5, 60, 30), "2"),
        (BoundingBox(10, 5, 20, 30), "a"),
        (BoundingBox(150, 5, 160, 30), "Z"),
    ]
    assert plate_text_from_boxes(plate, chars) == "A2"


def test_chars_to_ocr(tmp_path: Path) -> None:
    source = make_source(
        tmp_path / "raw",
        "fuente",
        NAMES,
        [
            ("train", "img1", noise(1, 100, 200), [PLATE, *CHARS]),
            ("train", "img2", noise(2, 100, 200), [PLATE, CHARS[1], CHARS[4], CHARS[3]]),
            ("valid", "img3", noise(1, 100, 200), [PLATE, *CHARS]),
        ],
    )
    out = tmp_path / "ocr"
    summary = chars_to_ocr(source, out, build_test_catalog())
    assert (
        summary.train_crops,
        summary.val_crops,
        summary.skipped,
        summary.dropped_duplicates,
    ) == (1, 0, 1, 1)
    rows = list(csv.DictReader((out / "train" / "annotations.csv").open(encoding="utf-8")))
    assert rows == [{"image_path": "images/fuente__img1_0.png", "plate_text": "ABC123"}]
    assert (out / "train" / "images" / "fuente__img1_0.png").exists()


def test_unknown_class(tmp_path: Path) -> None:
    source = make_source(tmp_path / "raw", "fuente", ["placa", "persona"], [])
    with pytest.raises(DatasetError):
        chars_to_ocr(source, tmp_path / "ocr", build_test_catalog())


ALT_CHARS = [
    "5 0.55 0.45 0.08 0.3",
    "0 0.20 0.45 0.08 0.3",
    "3 0.75 0.45 0.08 0.3",
    "2 0.40 0.45 0.08 0.3",
    "1 0.30 0.45 0.08 0.3",
    "4 0.65 0.45 0.08 0.3",
]


def test_train_only_source_is_split_by_group(tmp_path: Path) -> None:
    # sha256(grupo) % 10: gA -> 0 (val); gB -> 3 y gD -> 5 (train)
    source = make_source(
        tmp_path / "raw",
        "fuente",
        NAMES,
        [
            ("train", "gA.rf.a1", noise(1, 100, 200), [PLATE, *ALT_CHARS]),
            ("train", "gA.rf.b2", noise(2, 100, 200), [PLATE, *ALT_CHARS]),
            ("train", "gB.rf.c3", noise(3, 100, 200), [PLATE, *CHARS]),
            ("train", "gD.rf.d4", noise(4, 100, 200), [PLATE, *CHARS]),
        ],
    )
    out = tmp_path / "ocr"
    summary = chars_to_ocr(source, out, build_test_catalog())
    assert (
        summary.train_crops,
        summary.val_crops,
        summary.skipped,
        summary.dropped_duplicates,
    ) == (2, 2, 0, 0)
    val_rows = list(csv.DictReader((out / "val" / "annotations.csv").open(encoding="utf-8")))
    assert sorted(row["image_path"] for row in val_rows) == [
        "images/fuente__gA.rf.a1_0.png",
        "images/fuente__gA.rf.b2_0.png",
    ]
    assert {row["plate_text"] for row in val_rows} == {"ABC321"}


def test_group_split_drops_val_text_already_in_train(tmp_path: Path) -> None:
    source = make_source(
        tmp_path / "raw",
        "fuente",
        NAMES,
        [
            ("train", "gA.rf.a1", noise(1, 100, 200), [PLATE, *CHARS]),
            ("train", "gB.rf.c3", noise(3, 100, 200), [PLATE, *CHARS]),
        ],
    )
    summary = chars_to_ocr(source, tmp_path / "ocr", build_test_catalog())
    assert (
        summary.train_crops,
        summary.val_crops,
        summary.skipped,
        summary.dropped_duplicates,
    ) == (1, 0, 0, 1)
