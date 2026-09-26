from __future__ import annotations

import csv
import random
import re
from pathlib import Path

import numpy as np
import pytest

from ocr_training import synthetic_plates as sp
from ocr_training.common import TrainingError

pytestmark = pytest.mark.skipif(
    not sp.DEFAULT_FONT.exists(), reason="fuente Liberation Sans no instalada"
)
PATTERNS = {
    "LLLDDD": r"^[A-Z]{3}[0-9]{3}$",
    "LLLDDL": r"^[A-Z]{3}[0-9]{2}[A-Z]$",
    "DDDLLL": r"^[0-9]{3}[A-Z]{3}$",
}


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_random_text_follows_pattern(pattern: str) -> None:
    rng = random.Random(0)
    for _ in range(50):
        assert re.fullmatch(PATTERNS[pattern], sp.random_text(pattern, rng))


@pytest.mark.parametrize("style", sp.STYLES, ids=lambda s: s.name)
def test_render_sizes(style: sp.PlateStyle) -> None:
    image = sp.render_plate("ABC123", style, sp.DEFAULT_FONT, 0.5, random.Random(1))
    assert image.shape == (round(style.size_mm[1] * 0.5), round(style.size_mm[0] * 0.5), 3)
    assert image.dtype == np.uint8
    assert image.min() < 60  # hay texto oscuro sobre el fondo


def test_augment_keeps_shape() -> None:
    image = np.full((50, 110, 3), 200, np.uint8)
    out = sp.augment(image, random.Random(2))
    assert out.shape == image.shape and out.dtype == np.uint8


def test_missing_font() -> None:
    with pytest.raises(TrainingError):
        sp.render_plate("ABC123", sp.STYLES[0], Path("/no/existe.ttf"), 0.5, random.Random(0))


def test_generate_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    train, val = sp.generate_dataset(tmp_path / "syn", 10, 0.2, 7, sp.DEFAULT_FONT)
    assert (train, val) == (8, 2)
    rows = list(
        csv.DictReader((tmp_path / "syn" / "train" / "annotations.csv").open(encoding="utf-8"))
    )
    assert len(rows) == 8
    assert all((tmp_path / "syn" / "train" / r["image_path"]).exists() for r in rows)
    assert all(re.fullmatch(r"^[A-Z0-9]{6}$", r["plate_text"]) for r in rows)
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path / "syn", 10, 0.2, 7, sp.DEFAULT_FONT)
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path.parent / "fuera", 10, 0.2, 7, sp.DEFAULT_FONT)


def test_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    sp.generate_dataset(tmp_path / "a", 3, 0.0, 5, sp.DEFAULT_FONT)
    sp.generate_dataset(tmp_path / "b", 3, 0.0, 5, sp.DEFAULT_FONT)
    first = (tmp_path / "a" / "train" / "annotations.csv").read_text(encoding="utf-8")
    assert first == (tmp_path / "b" / "train" / "annotations.csv").read_text(encoding="utf-8")
    assert (tmp_path / "a" / "train" / "images" / "syn_000000.png").read_bytes() == (
        tmp_path / "b" / "train" / "images" / "syn_000000.png"
    ).read_bytes()
