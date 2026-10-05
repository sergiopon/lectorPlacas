"""Tests de aceptación adicionales.

Viven en `training/ocr/tests/` y no en `tests/review/` porque `training/ocr` es un
proyecto uv independiente que el pytest de la raíz no recoge.

Cubren lo que el test de aceptación no fija: el redondeo de `val_fraction`, el reparto
por índice, la forma por estilo y que un fallo de fuente no deje una salida a medias.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import pytest

from ocr_training import synthetic_plates as sp
from ocr_training.common import TrainingError

pytestmark = pytest.mark.skipif(
    not sp.DEFAULT_FONT.exists(), reason="fuente Liberation Sans no instalada"
)


def annotations(output_dir: Path, split: str) -> list[dict[str, str]]:
    with (output_dir / split / "annotations.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_val_fraction_rounds_and_may_be_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`round(count * val_fraction)` decide el tamaño de `val`, incluso si da cero."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    assert sp.generate_dataset(tmp_path / "uno", 3, 0.1, 1, sp.DEFAULT_FONT) == (3, 0)
    assert sp.generate_dataset(tmp_path / "dos", 12, 0.25, 1, sp.DEFAULT_FONT) == (9, 3)


def test_the_first_indices_go_to_val(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Las muestras de `val` son las de índice menor, no una selección intercalada."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    output = tmp_path / "syn"
    sp.generate_dataset(output, 10, 0.2, 0, sp.DEFAULT_FONT)
    assert sorted(row["image_path"] for row in annotations(output, "val")) == [
        "images/syn_000000.png",
        "images/syn_000001.png",
    ]
    assert min(row["image_path"] for row in annotations(output, "train")) == "images/syn_000002.png"


def test_styles_keep_their_aspect_ratio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada imagen usa el tamaño real de su estilo: carro 330x160 y moto 235x105."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    output = tmp_path / "syn"
    sp.generate_dataset(output, 3, 0.0, 4, sp.DEFAULT_FONT)
    car = cv2.imread(str(output / "train" / "images" / "syn_000000.png"))
    moto = cv2.imread(str(output / "train" / "images" / "syn_000002.png"))
    assert abs(car.shape[1] / car.shape[0] - 330 / 160) < 0.05
    assert abs(moto.shape[1] / moto.shape[0] - 235 / 105) < 0.05


def test_invalid_count_does_not_create_the_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un `count` inválido falla antes de crear el directorio de salida."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path / "vacio", 0, 0.1, 0, sp.DEFAULT_FONT)
    assert not (tmp_path / "vacio").exists()
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path / "frac", 5, 1.0, 0, sp.DEFAULT_FONT)
    assert not (tmp_path / "frac").exists()


def test_main_fails_loudly_with_a_missing_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una fuente inexistente es un error, no un dataset silenciosamente vacío."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    with pytest.raises(TrainingError, match="fuente no disponible"):
        sp.main(["--output", "syn", "--count", "2", "--font", "/no/existe.ttf"])


def test_annotations_and_images_agree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada fila del CSV apunta a una imagen escrita, y el conteo coincide con los archivos."""
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    output = tmp_path / "syn"
    sp.generate_dataset(output, 6, 0.5, 2, sp.DEFAULT_FONT)
    for split, expected in (("train", 3), ("val", 3)):
        rows = annotations(output, split)
        assert len(rows) == expected
        assert len(list((output / split / "images").glob("*.png"))) == expected
        assert all((output / split / row["image_path"]).is_file() for row in rows)
        assert all(row["image_path"].startswith("images/") for row in rows)
