"""Tests de aceptación adicionales.

Cubren casos borde que la spec no enumera: recorte de cajas al borde de la imagen,
estrictura del formato YOLO y del manifiesto de fuentes, qué se considera duplicado
(solo `val`) y qué pasa con las imágenes sin archivo de etiquetas.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.chars_to_ocr import chars_to_ocr, plate_text_from_boxes
from lector_placas.datasets.merge_detection import merge_detection
from lector_placas.datasets.sources import load_sources
from lector_placas.datasets.yolo_format import (
    YoloBox,
    parse_label_file,
    read_class_names,
    yolo_to_pixels,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError
from tests.fixtures.plate_catalog import build_test_catalog
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
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_yolo_to_pixels_clips_to_the_image() -> None:
    """Una caja que sobresale se recorta a la imagen; una sin área devuelve `None`."""
    assert yolo_to_pixels(YoloBox(0, 1.0, 0.5, 0.5, 0.5), 100, 100) == BoundingBox(
        75.0, 25.0, 100.0, 75.0
    )
    assert yolo_to_pixels(YoloBox(0, 0.5, 0.5, 1.0, 1.0), 100, 50) == BoundingBox(
        0.0, 0.0, 100.0, 50.0
    )
    assert yolo_to_pixels(YoloBox(0, 0.5, 0.5, 0.5, 0.5), 0, 100) is None
    assert yolo_to_pixels(YoloBox(0, 0.5, 0.5, 0.5, 0.5), 100, 0) is None


def test_parse_label_file_rejects_extra_fields(tmp_path: Path) -> None:
    """El formato exige exactamente cinco campos: una confianza extra es un error."""
    label = tmp_path / "a.txt"
    label.write_text("0 0.5 0.5 0.2 0.1 0.9\n", encoding="utf-8")
    with pytest.raises(DatasetError):
        parse_label_file(label)


def test_read_class_names_rejects_non_integer_keys(tmp_path: Path) -> None:
    """Un mapa de clases con claves no enteras no es un `data.yaml` válido."""
    data = tmp_path / "data.yaml"
    data.write_text(yaml.safe_dump({"names": {"placa": "Placas"}}), encoding="utf-8")
    with pytest.raises(DatasetError):
        read_class_names(data)


def test_sources_reject_duplicate_names_and_unsafe_paths(tmp_path: Path) -> None:
    """El manifiesto no admite nombres repetidos ni rutas absolutas o con `..`."""
    base = {
        "name": "alfa",
        "path": "alfa",
        "url": "https://example.org/alfa",
        "license": "MIT",
        "plate_classes": ["placa"],
    }
    duplicated = tmp_path / "dup.yaml"
    duplicated.write_text(yaml.safe_dump({"version": 1, "sources": [base, base]}), encoding="utf-8")
    with pytest.raises(DatasetError):
        load_sources(duplicated)
    for unsafe in ("/datos/alfa", "../alfa"):
        escaped = tmp_path / "esc.yaml"
        escaped.write_text(
            yaml.safe_dump({"version": 1, "sources": [{**base, "path": unsafe}]}),
            encoding="utf-8",
        )
        with pytest.raises(DatasetError):
            load_sources(escaped)


def test_train_images_are_never_deduplicated(tmp_path: Path) -> None:
    """La deduplicación por dHash solo descarta `val`; dos train idénticos se conservan."""
    raw = tmp_path / "raw"
    make_source(
        raw,
        "alfa",
        ["car", "placa"],
        [
            ("train", "a1", noise(1), ["1 0.5 0.5 0.2 0.1"]),
            ("train", "a2", noise(1), ["1 0.5 0.5 0.2 0.1"]),
        ],
    )
    summary = merge_detection(sources_file(tmp_path, ["placa"]), raw, tmp_path / "merged")
    assert (summary.train_images, summary.dropped_duplicates) == (2, 0)


def test_val_is_deduplicated_against_other_val(tmp_path: Path) -> None:
    """Un `val` idéntico a otro `val` ya aceptado también se descarta."""
    raw = tmp_path / "raw"
    make_source(
        raw,
        "alfa",
        ["car", "placa"],
        [
            ("train", "a1", noise(1), ["1 0.5 0.5 0.2 0.1"]),
            ("valid", "v1", noise(42), ["1 0.5 0.5 0.2 0.1"]),
            ("valid", "v2", noise(42), ["1 0.5 0.5 0.2 0.1"]),
        ],
    )
    summary = merge_detection(sources_file(tmp_path, ["placa"]), raw, tmp_path / "merged")
    assert (summary.val_images, summary.dropped_duplicates) == (1, 1)


def test_images_without_labels_are_kept_as_negatives(tmp_path: Path) -> None:
    """Una imagen sin archivo de etiquetas se copia y se marca como negativo."""
    raw = tmp_path / "raw"
    source = make_source(
        raw,
        "alfa",
        ["car", "placa"],
        [
            ("train", "a1", noise(1), ["1 0.5 0.5 0.2 0.1"]),
            ("train", "a2", noise(2), ["1 0.5 0.5 0.2 0.1"]),
        ],
    )
    (source / "train" / "labels" / "a2.txt").unlink()
    output = tmp_path / "merged"
    summary = merge_detection(sources_file(tmp_path, ["placa"]), raw, output)
    assert summary.train_images == 2
    assert (output / "labels" / "train" / "alfa__a2.txt").read_text() == ""
    assert (output / "images" / "train" / "alfa__a2.png").exists()


def test_plate_text_from_boxes_includes_border_characters() -> None:
    """Un carácter cuyo centro cae justo en el borde de la placa cuenta como dentro."""
    plate = BoundingBox(10.0, 0.0, 100.0, 40.0)
    border = (BoundingBox(0.0, 10.0, 20.0, 30.0), "A")
    outside = (BoundingBox(90.0, 10.0, 130.0, 30.0), "B")
    assert plate_text_from_boxes(plate, [outside, border]) == "A"


def test_chars_to_ocr_skips_text_without_a_matching_format(tmp_path: Path) -> None:
    """Un texto que no encaja en ningún formato del catálogo se cuenta como omitido."""
    plate_box = "6 0.5 0.5 0.8 0.6"
    chars = [
        "0 0.20 0.45 0.08 0.3",  # A
        "1 0.30 0.45 0.08 0.3",  # B
        "2 0.40 0.45 0.08 0.3",  # 1
        "3 0.55 0.45 0.08 0.3",  # 2
        "4 0.65 0.45 0.08 0.3",  # 3
        "5 0.75 0.45 0.08 0.3",  # 4
    ]
    names = ["A", "B", "1", "2", "3", "4", "placa"]
    raw = tmp_path / "raw"
    make_source(raw, "fuente", names, [("train", "img1", noise(7, 100, 200), [plate_box, *chars])])
    output = tmp_path / "ocr"
    summary = chars_to_ocr(raw / "fuente", output, build_test_catalog())
    assert (summary.train_crops, summary.skipped) == (0, 1)
    assert not output.exists() or not list(output.rglob("annotations.csv"))


def test_chars_to_ocr_writes_only_accepted_splits(tmp_path: Path) -> None:
    """Si `val` queda vacío tras descartar duplicados, no se escribe su CSV."""
    plate_box = "6 0.5 0.5 0.8 0.6"
    chars = [
        "3 0.55 0.45 0.08 0.3",
        "0 0.20 0.45 0.08 0.3",
        "5 0.75 0.45 0.08 0.3",
        "2 0.40 0.45 0.08 0.3",
        "1 0.30 0.45 0.08 0.3",
        "4 0.65 0.45 0.08 0.3",
    ]
    names = ["A", "B", "C", "1", "2", "3", "placa"]
    raw = tmp_path / "raw"
    make_source(
        raw,
        "fuente",
        names,
        [
            ("train", "img1", noise(3, 100, 200), [plate_box, *chars]),
            ("valid", "img2", noise(3, 100, 200), [plate_box, *chars]),
        ],
    )
    output = tmp_path / "ocr"
    summary = chars_to_ocr(raw / "fuente", output, build_test_catalog())
    assert (summary.train_crops, summary.val_crops, summary.dropped_duplicates) == (1, 0, 1)
    rows = list(csv.DictReader((output / "train" / "annotations.csv").open(encoding="utf-8")))
    assert rows == [{"image_path": "images/fuente__img1_0.png", "plate_text": "ABC123"}]
    assert not (output / "val").exists()
