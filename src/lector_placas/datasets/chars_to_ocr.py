"""Conversión de un dataset de detección por carácter en recortes de placa para el OCR."""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import cv2

from lector_placas.application.image_ops import crop_image
from lector_placas.application.ports import ImageBGR
from lector_placas.datasets.dhash import dhash, hamming
from lector_placas.datasets.merge_detection import (
    DUPLICATE_DISTANCE,
    IMAGE_SUFFIXES,
    SPLIT_MAP,
)
from lector_placas.datasets.yolo_format import parse_label_file, read_class_names, yolo_to_pixels
from lector_placas.domain.entities import PLATE_TEXT_REGEX, BoundingBox
from lector_placas.domain.errors import DatasetError
from lector_placas.domain.plate_formats import PlateFormatCatalog
from lector_placas.infrastructure.paths import ensure_private_dir

PLATE_CLASS: Final[str] = "placa"
IGNORED_CLASSES: Final[frozenset[str]] = frozenset({"ciudad"})
ANNOTATIONS_HEADER: Final[tuple[str, ...]] = ("image_path", "plate_text")
_OUTPUT_SPLITS: Final[tuple[str, ...]] = ("train", "val")
_CHAR_CLASS_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Za-z]$")


@dataclass(frozen=True, slots=True)
class OcrSummary:
    """Conteos de los recortes de placa convertidos para el OCR."""

    train_crops: int
    val_crops: int
    skipped: int
    dropped_duplicates: int


@dataclass(frozen=True, slots=True)
class _Crop:
    """Recorte de placa aceptado, con su texto y su partición de destino."""

    split: str
    output_name: str
    text: str
    image: ImageBGR
    image_hash: int


@dataclass(frozen=True, slots=True)
class _SplitContext:
    """Clases relevantes y parámetros comunes al procesar las imágenes de un split."""

    plate_ids: frozenset[int]
    char_classes: Mapping[int, str]
    source: str
    output_split: str
    catalog: PlateFormatCatalog


def plate_text_from_boxes(plate: BoundingBox, chars: Sequence[tuple[BoundingBox, str]]) -> str:
    """Concatena en mayúsculas los caracteres cuyo centro cae dentro de la placa.

    Args:
        plate: caja de la placa en píxeles.
        chars: pares (caja del carácter, texto) en píxeles.

    Returns:
        El texto ordenado por el centro horizontal de cada carácter.
    """
    inside = [((box.x1 + box.x2) / 2.0, text) for box, text in chars if _center_inside(plate, box)]
    inside.sort()
    return "".join(text.upper() for _, text in inside)


def chars_to_ocr(source_dir: Path, output_dir: Path, catalog: PlateFormatCatalog) -> OcrSummary:
    """Convierte un dataset anotado por carácter en recortes de placa con su texto.

    Args:
        source_dir: directorio del dataset de origen, con su `data.yaml`.
        output_dir: directorio de salida; debe estar vacío o no existir.
        catalog: catálogo de formatos usado para descartar textos que no son placas.

    Returns:
        Los conteos de recortes de train y val, descartes y duplicados.

    Raises:
        DatasetError: si la salida no está vacía, hay clases desconocidas o una
            imagen no se puede leer.
    """
    _require_empty(output_dir)
    ensure_private_dir(output_dir)
    names = read_class_names(source_dir / "data.yaml")
    _validate_classes(names)
    train, val, skipped = _collect(source_dir, names, catalog)
    kept_val, dropped = _deduplicate(train, val)
    _write_crops((*train, *kept_val), output_dir)
    return OcrSummary(len(train), len(kept_val), skipped, dropped)


def _validate_classes(names: Mapping[int, str]) -> None:
    """Exige que toda clase sea la placa, una ignorada o un carácter.

    Raises:
        DatasetError: si alguna clase no encaja en esas categorías.
    """
    for name in names.values():
        if name == PLATE_CLASS or name in IGNORED_CLASSES:
            continue
        if _CHAR_CLASS_REGEX.fullmatch(name) is None:
            raise DatasetError(f"clase desconocida: {name}")


def _collect(
    source_dir: Path, names: Mapping[int, str], catalog: PlateFormatCatalog
) -> tuple[list[_Crop], list[_Crop], int]:
    """Recolecta los recortes de train y val, y cuántos textos se descartaron."""
    plate_ids = frozenset(index for index, name in names.items() if name == PLATE_CLASS)
    char_classes = {
        index: name for index, name in names.items() if _CHAR_CLASS_REGEX.fullmatch(name)
    }
    train: list[_Crop] = []
    val: list[_Crop] = []
    skipped = 0
    for input_split, output_split in SPLIT_MAP.items():
        images_dir = source_dir / input_split / "images"
        if not images_dir.is_dir():
            continue
        context = _SplitContext(plate_ids, char_classes, source_dir.name, output_split, catalog)
        for image_path in sorted(
            path for path in images_dir.iterdir() if path.suffix in IMAGE_SUFFIXES
        ):
            label_path = source_dir / input_split / "labels" / f"{image_path.stem}.txt"
            crops, image_skipped = _image_crops(image_path, label_path, context)
            skipped += image_skipped
            if output_split == "train":
                train.extend(crops)
            else:
                val.extend(crops)
    return train, val, skipped


def _image_crops(
    image_path: Path, label_path: Path, context: _SplitContext
) -> tuple[list[_Crop], int]:
    """Extrae los recortes de placa válidos de una imagen y cuenta los descartados.

    Raises:
        DatasetError: si la imagen no se puede leer con OpenCV.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise DatasetError(f"no se pudo leer la imagen: {image_path.name}")
    frame = cast(ImageBGR, image)
    height, width = frame.shape[0], frame.shape[1]
    boxes = parse_label_file(label_path)
    pixels = [yolo_to_pixels(box, width, height) for box in boxes]
    chars = [
        (box_pixels, context.char_classes[box.class_id])
        for box, box_pixels in zip(boxes, pixels, strict=True)
        if box_pixels is not None and box.class_id in context.char_classes
    ]
    crops: list[_Crop] = []
    skipped = 0
    for index, (box, box_pixels) in enumerate(zip(boxes, pixels, strict=True)):
        if box_pixels is None or box.class_id not in context.plate_ids:
            continue
        text = plate_text_from_boxes(box_pixels, chars)
        if PLATE_TEXT_REGEX.fullmatch(text) is None or not context.catalog.matching(text):
            skipped += 1
            continue
        crop = crop_image(frame, box_pixels)
        crops.append(
            _Crop(
                context.output_split,
                f"{context.source}__{image_path.stem}_{index}",
                text,
                crop,
                dhash(crop),
            )
        )
    return crops, skipped


def _deduplicate(train: list[_Crop], val: list[_Crop]) -> tuple[list[_Crop], int]:
    """Descarta los recortes de val casi duplicados de train o de otro val aceptado.

    Returns:
        Los recortes de val conservados y cuántos se descartaron.
    """
    accepted = [entry.image_hash for entry in train]
    kept: list[_Crop] = []
    dropped = 0
    for entry in val:
        if any(hamming(entry.image_hash, other) <= DUPLICATE_DISTANCE for other in accepted):
            dropped += 1
            continue
        kept.append(entry)
        accepted.append(entry.image_hash)
    return kept, dropped


def _write_crops(entries: Sequence[_Crop], output_dir: Path) -> None:
    """Escribe los recortes PNG del split y su `annotations.csv` (formato fast-plate-ocr)."""
    for split in _OUTPUT_SPLITS:
        subset = [entry for entry in entries if entry.split == split]
        if not subset:
            continue
        images_dir = ensure_private_dir(output_dir / split / "images")
        with (output_dir / split / "annotations.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(ANNOTATIONS_HEADER)
            for entry in subset:
                name = f"{entry.output_name}.png"
                cv2.imwrite(str(images_dir / name), entry.image)
                writer.writerow([f"images/{name}", entry.text])


def _center_inside(plate: BoundingBox, box: BoundingBox) -> bool:
    """Indica si el centro de `box` está dentro de `plate`, bordes incluidos."""
    center_x = (box.x1 + box.x2) / 2.0
    center_y = (box.y1 + box.y2) / 2.0
    return plate.x1 <= center_x <= plate.x2 and plate.y1 <= center_y <= plate.y2


def _require_empty(output_dir: Path) -> None:
    """Exige que el directorio de salida no exista o esté vacío.

    Raises:
        DatasetError: si la ruta existe y no es un directorio vacío.
    """
    if not output_dir.exists():
        return
    if not output_dir.is_dir() or any(output_dir.iterdir()):
        raise DatasetError("el directorio de salida no está vacío")
