"""Iteración de un split de dataset YOLO con sus etiquetas en píxeles."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import cv2

from lector_placas.application.ports import ImageBGR
from lector_placas.datasets.yolo_format import parse_label_file, yolo_to_pixels
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError
from lector_placas.infrastructure.paths import resolve_within

IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
SPLITS: Final[frozenset[str]] = frozenset({"train", "val"})


@dataclass(frozen=True, slots=True)
class LabeledImage:
    """Imagen del dataset con sus placas anotadas en píxeles."""

    name: str
    image: ImageBGR
    boxes: tuple[BoundingBox, ...]


def iter_split(dataset_dir: Path, split: str) -> Iterator[LabeledImage]:
    """Recorre las imágenes de un split con sus cajas convertidas a píxeles.

    Args:
        dataset_dir: raíz del dataset YOLO (`images/` y `labels/`).
        split: `"train"` o `"val"`.

    Yields:
        Cada imagen legible del split en orden de nombre; una imagen sin archivo de
        etiquetas se entrega sin cajas.

    Raises:
        DatasetError: si el split no es válido, su carpeta de imágenes no existe o
            una imagen no se puede decodificar.
    """
    if split not in SPLITS:
        raise DatasetError(f"split inválido: {split}")
    images_dir = resolve_within(dataset_dir, Path("images") / split)
    if not images_dir.is_dir():
        raise DatasetError(f"no existe el split {split}")
    for path in sorted(images_dir.iterdir(), key=_by_name):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield _load_image(dataset_dir, split, path)


def _by_name(path: Path) -> str:
    """Clave de ordenación: nombre del archivo."""
    return path.name


def _load_image(dataset_dir: Path, split: str, path: Path) -> LabeledImage:
    """Carga una imagen y sus cajas en píxeles; las cajas vacías se descartan.

    Raises:
        DatasetError: si `cv2` no puede decodificar la imagen.
    """
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise DatasetError(f"imagen ilegible: {path.name}")
    frame = cast(ImageBGR, image)
    height, width = frame.shape[0], frame.shape[1]
    label_path = resolve_within(dataset_dir, Path("labels") / split / f"{path.stem}.txt")
    boxes = tuple(
        pixels
        for box in parse_label_file(label_path)
        if (pixels := yolo_to_pixels(box, width, height)) is not None
    )
    return LabeledImage(path.name, frame, boxes)
