from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.yolo_format import (
    YoloBox,
    format_labels,
    parse_label_file,
    read_class_names,
    yolo_to_pixels,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError


def test_parse_and_format(tmp_path: Path) -> None:
    label = tmp_path / "a.txt"
    label.write_text("1 0.5 0.5 0.2 0.1\n\n0 0.25 0.25 0.5 0.5\n", encoding="utf-8")
    boxes = parse_label_file(label)
    assert boxes == [YoloBox(1, 0.5, 0.5, 0.2, 0.1), YoloBox(0, 0.25, 0.25, 0.5, 0.5)]
    assert format_labels(boxes[:1]) == "1 0.500000 0.500000 0.200000 0.100000\n"
    assert format_labels([]) == ""
    assert parse_label_file(tmp_path / "missing.txt") == []


@pytest.mark.parametrize(
    "line",
    [
        "1 0.5 0.5 0.2",
        "x 0.5 0.5 0.2 0.1",
        "1 1.5 0.5 0.2 0.1",
        "1 0.5 0.5 0 0.1",
        "1 0.5 0.5 0.2 0.1 0.3",
        "1 0.2 0.2 0.6 0.2 0.2 0.2",
    ],
)
def test_invalid_lines(tmp_path: Path, line: str) -> None:
    label = tmp_path / "b.txt"
    label.write_text(line, encoding="utf-8")
    with pytest.raises(DatasetError):
        parse_label_file(label)


def test_polygon_becomes_bounding_box(tmp_path: Path) -> None:
    label = tmp_path / "p.txt"
    label.write_text("3 0.2 0.2 0.6 0.2 0.6 0.4 0.2 0.4\n1 0.5 0.5 0.2 0.1", encoding="utf-8")
    polygon, box = parse_label_file(label)
    assert polygon.class_id == 3
    assert (polygon.cx, polygon.cy, polygon.w, polygon.h) == pytest.approx((0.4, 0.3, 0.4, 0.2))
    assert box == YoloBox(1, 0.5, 0.5, 0.2, 0.1)


def test_pixels_and_names(tmp_path: Path) -> None:
    assert yolo_to_pixels(YoloBox(0, 0.5, 0.5, 0.5, 0.5), 200, 100) == BoundingBox(
        50.0, 25.0, 150.0, 75.0
    )
    data = tmp_path / "data.yaml"
    data.write_text(yaml.safe_dump({"names": ["car", "placa"]}), encoding="utf-8")
    assert read_class_names(data) == {0: "car", 1: "placa"}
    data.write_text(yaml.safe_dump({"names": {0: "Placas"}}), encoding="utf-8")
    assert read_class_names(data) == {0: "Placas"}
    data.write_text(yaml.safe_dump({"names": "x"}), encoding="utf-8")
    with pytest.raises(DatasetError):
        read_class_names(data)
