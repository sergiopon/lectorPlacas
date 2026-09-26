from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml


def noise(seed: int, height: int = 64, width: int = 96) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (height, width, 3), dtype=np.uint8)


def make_source(
    root: Path, name: str, names: object, items: list[tuple[str, str, np.ndarray, list[str]]]
) -> Path:
    source = root / name
    source.mkdir(parents=True)
    (source / "data.yaml").write_text(yaml.safe_dump({"names": names}), encoding="utf-8")
    for split, stem, image, lines in items:
        (source / split / "images").mkdir(parents=True, exist_ok=True)
        (source / split / "labels").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(source / split / "images" / f"{stem}.png"), image)
        (source / split / "labels" / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    return source
