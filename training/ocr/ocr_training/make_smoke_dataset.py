from __future__ import annotations

import argparse
import csv
import random
import string
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from ocr_training.common import DATASETS_DIR, TrainingError

_LETTERS: str = string.ascii_uppercase
_DIGITS: str = string.digits
_PATTERNS: tuple[str, ...] = ("LLLDDD", "LLLDDL")
_IMAGE_SHAPE: tuple[int, int, int] = (64, 128, 3)
_BACKGROUND_BGR: tuple[int, int, int] = (0, 200, 255)
_TEXT_BGR: tuple[int, int, int] = (0, 0, 0)
_TEXT_ORIGIN: tuple[int, int] = (4, 44)
_FONT_SCALE: float = 0.9
_FONT_THICKNESS: int = 2


def _random_text(rng: random.Random, pattern: str) -> str:
    """Genera un texto de placa sintético siguiendo un patrón `L`/`D`.

    Args:
        rng: Generador aleatorio determinista.
        pattern: Patrón con `L` (letra) y `D` (dígito).

    Returns:
        Texto generado.
    """
    return "".join(rng.choice(_LETTERS) if char == "L" else rng.choice(_DIGITS) for char in pattern)


def _write_split(split_dir: Path, count: int, rng: random.Random) -> None:
    """Genera un split (imágenes + `annotations.csv`) del dataset sintético.

    Args:
        split_dir: Directorio del split (`train` o `val`).
        count: Número de muestras a generar.
        rng: Generador aleatorio determinista.
    """
    images_dir = split_dir / "images"
    images_dir.mkdir(parents=True)
    rows: list[tuple[str, str]] = []
    for index in range(count):
        pattern = _PATTERNS[index % len(_PATTERNS)]
        text = _random_text(rng, pattern)
        image = np.zeros(_IMAGE_SHAPE, dtype=np.uint8)
        image[:, :] = _BACKGROUND_BGR
        cv2.putText(
            image,
            text,
            _TEXT_ORIGIN,
            cv2.FONT_HERSHEY_SIMPLEX,
            _FONT_SCALE,
            _TEXT_BGR,
            _FONT_THICKNESS,
        )
        image_path = images_dir / f"{index}.png"
        cv2.imwrite(str(image_path), image)
        rows.append((f"images/{index}.png", text))

    with (split_dir / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("image_path", "plate_text"))
        writer.writerows(rows)


def make_smoke_dataset(output_dir: Path, train_count: int, val_count: int, seed: int) -> None:
    """Genera un dataset sintético mínimo para el smoke test del entrenamiento.

    Args:
        output_dir: Directorio de salida, debe estar dentro de `DATASETS_DIR` y
            no existir.
        train_count: Número de muestras del split `train`.
        val_count: Número de muestras del split `val`.
        seed: Semilla del generador aleatorio.

    Raises:
        TrainingError: si `output_dir` no está dentro de `DATASETS_DIR` o ya existe.
    """
    resolved = output_dir.resolve()
    datasets_root = DATASETS_DIR.resolve()
    if datasets_root not in resolved.parents and resolved != datasets_root:
        raise TrainingError(f"output_dir fuera de DATASETS_DIR: {output_dir}")
    if resolved.exists():
        raise TrainingError(f"output_dir ya existe: {output_dir}")

    rng = random.Random(seed)
    _write_split(resolved / "train", train_count, rng)
    _write_split(resolved / "val", val_count, rng)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI para generar el dataset sintético de smoke test.

    Args:
        argv: Argumentos de línea de comandos (por defecto `sys.argv[1:]`).

    Returns:
        Código de salida: 0 si el dataset se genera correctamente.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("smoke"))
    parser.add_argument("--train-count", type=int, default=64)
    parser.add_argument("--val-count", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    output_dir = DATASETS_DIR / args.output
    make_smoke_dataset(output_dir, args.train_count, args.val_count, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
