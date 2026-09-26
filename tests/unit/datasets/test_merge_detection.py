from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.merge_detection import merge_detection
from lector_placas.datasets.sources import load_sources
from lector_placas.domain.errors import DatasetError
from tests.unit.datasets.synthetic import make_source, noise


def sources_file(tmp_path: Path, alfa_classes: list[str]) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "sources": [
                    {
                        "name": "alfa",
                        "path": "alfa",
                        "url": "https://example.org/alfa",
                        "license": "CC BY 4.0",
                        "plate_classes": alfa_classes,
                    },
                    {
                        "name": "beta",
                        "path": "beta",
                        "url": "https://example.org/beta",
                        "license": "MIT",
                        "plate_classes": ["Placas"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def build_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    make_source(
        raw,
        "alfa",
        ["car", "placa"],
        [
            ("train", "a1", noise(1), ["1 0.5 0.5 0.2 0.1", "0 0.3 0.3 0.2 0.2"]),
            ("train", "a2", noise(2), ["0 0.5 0.5 0.4 0.4"]),
            ("valid", "a3", noise(1), ["1 0.5 0.5 0.2 0.1"]),
            ("test", "a4", noise(4), ["1 0.5 0.5 0.1 0.1"]),
        ],
    )
    make_source(raw, "beta", {0: "Placas"}, [("train", "b1", noise(5), ["0 0.5 0.5 0.3 0.1"])])
    return raw


def test_merge_detection(tmp_path: Path) -> None:
    out = tmp_path / "merged"
    summary = merge_detection(sources_file(tmp_path, ["placa"]), build_raw(tmp_path), out)
    assert (
        summary.train_images,
        summary.val_images,
        summary.dropped_duplicates,
        summary.boxes,
    ) == (3, 1, 1, 3)
    assert (
        out / "labels" / "train" / "alfa__a1.txt"
    ).read_text() == "0 0.500000 0.500000 0.200000 0.100000\n"
    assert (out / "labels" / "train" / "alfa__a2.txt").read_text() == ""
    assert (out / "images" / "val" / "alfa__a4.png").exists()
    assert not (out / "images" / "val" / "alfa__a3.png").exists()
    data = yaml.safe_load((out / "data.yaml").read_text())
    assert data["names"] == {0: "plate"} and data["val"] == "images/val"
    rows = list(csv.DictReader((out / "provenance.csv").open(encoding="utf-8")))
    assert len(rows) == 4 and {r["source"] for r in rows} == {"alfa", "beta"}


def test_merge_errors(tmp_path: Path) -> None:
    raw = build_raw(tmp_path)
    with pytest.raises(DatasetError):
        merge_detection(sources_file(tmp_path, ["plate"]), raw, tmp_path / "o1")
    out = tmp_path / "o2"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(DatasetError):
        merge_detection(sources_file(tmp_path, ["placa"]), raw, out)


def test_placeholder_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatasetError):
        load_sources(sources_file(tmp_path, ["COMPLETAR"]))
