"""Unión de datasets de detección de placas en un único dataset YOLO de una clase."""

from __future__ import annotations

import csv
import hashlib
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

import cv2
import yaml

from lector_placas.application.ports import ImageBGR
from lector_placas.datasets.dhash import dhash, hamming
from lector_placas.datasets.sources import SourcesFile, load_sources
from lector_placas.datasets.yolo_format import (
    YoloBox,
    format_labels,
    parse_label_file,
    read_class_names,
)
from lector_placas.domain.errors import DatasetError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

SPLIT_MAP: Final[Mapping[str, str]] = MappingProxyType(
    {"train": "train", "valid": "val", "test": "val"}
)
IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
DUPLICATE_DISTANCE: Final[int] = 4
PLATE_CLASS_NAME: Final[str] = "plate"
PROVENANCE_HEADER: Final[tuple[str, ...]] = (
    "split",
    "output_name",
    "source",
    "original_path",
    "sha256",
)


@dataclass(frozen=True, slots=True)
class MergeSummary:
    """Conteos del dataset de detección unificado."""

    train_images: int
    val_images: int
    dropped_duplicates: int
    boxes: int


@dataclass(frozen=True, slots=True)
class _Entry:
    """Imagen de una fuente y su etiqueta ya remapeada a la clase 0."""

    split: str
    source: str
    stem: str
    image_path: Path
    boxes: tuple[YoloBox, ...]
    image_hash: int


def merge_detection(sources_file: Path, raw_root: Path, output_dir: Path) -> MergeSummary:
    """Une las fuentes de detección en un dataset YOLO de una sola clase.

    Args:
        sources_file: ruta del manifiesto de fuentes.
        raw_root: directorio con los datasets descargados, uno por fuente.
        output_dir: directorio de salida; debe estar vacío o no existir.

    Returns:
        Los conteos de imágenes de train y val, duplicados descartados y cajas escritas.

    Raises:
        DatasetError: si la salida no está vacía, una fuente no tiene las clases de
            placa declaradas o una imagen no se puede leer.
    """
    _require_empty(output_dir)
    ensure_private_dir(output_dir)
    train, val = _collect(load_sources(sources_file), raw_root)
    kept_val, dropped = _deduplicate(train, val)
    boxes = _write_entries(train, "train", output_dir) + _write_entries(kept_val, "val", output_dir)
    _write_data_yaml(output_dir)
    _write_provenance((*train, *kept_val), output_dir, raw_root)
    return MergeSummary(len(train), len(kept_val), dropped, boxes)


def _collect(sources: SourcesFile, raw_root: Path) -> tuple[list[_Entry], list[_Entry]]:
    """Recolecta las entradas de train y val de todas las fuentes, en su orden."""
    train: list[_Entry] = []
    val: list[_Entry] = []
    for source in sources.sources:
        source_dir = resolve_within(raw_root, source.path)
        names = read_class_names(source_dir / "data.yaml")
        plate_ids = _plate_ids(source.plate_classes, names)
        for input_split, output_split in SPLIT_MAP.items():
            entries = _collect_split(source_dir, source.name, input_split, plate_ids)
            if output_split == "train":
                train.extend(entries)
            else:
                val.extend(entries)
    return train, val


def _plate_ids(plate_classes: Sequence[str], names: Mapping[int, str]) -> frozenset[int]:
    """Traduce los nombres de clase de placa a sus identificadores en el `data.yaml`.

    Raises:
        DatasetError: si algún nombre declarado no existe en `names`.
    """
    ids_by_name = {name: index for index, name in names.items()}
    missing = [name for name in plate_classes if name not in ids_by_name]
    if missing:
        raise DatasetError(f"clase de placa ausente en data.yaml: {', '.join(missing)}")
    return frozenset(ids_by_name[name] for name in plate_classes)


def _collect_split(
    source_dir: Path, source_name: str, input_split: str, plate_ids: frozenset[int]
) -> list[_Entry]:
    """Recolecta las imágenes de un split de una fuente, con sus cajas de placa.

    Raises:
        DatasetError: si una imagen no se puede leer con OpenCV.
    """
    images_dir = source_dir / input_split / "images"
    if not images_dir.is_dir():
        return []
    entries: list[_Entry] = []
    for image_path in sorted(
        path for path in images_dir.iterdir() if path.suffix in IMAGE_SUFFIXES
    ):
        image = cv2.imread(str(image_path))
        if image is None:
            raise DatasetError(f"no se pudo leer la imagen: {image_path.name}")
        label_path = source_dir / input_split / "labels" / f"{image_path.stem}.txt"
        boxes = tuple(
            YoloBox(0, box.cx, box.cy, box.w, box.h)
            for box in parse_label_file(label_path)
            if box.class_id in plate_ids
        )
        entries.append(
            _Entry(
                SPLIT_MAP[input_split],
                source_name,
                image_path.stem,
                image_path,
                boxes,
                dhash(cast(ImageBGR, image)),
            )
        )
    return entries


def _deduplicate(train: list[_Entry], val: list[_Entry]) -> tuple[list[_Entry], int]:
    """Descarta las entradas de val casi duplicadas de train o de otro val aceptado.

    Returns:
        Las entradas de val conservadas y cuántas se descartaron.
    """
    accepted = [entry.image_hash for entry in train]
    kept: list[_Entry] = []
    dropped = 0
    for entry in val:
        if any(hamming(entry.image_hash, other) <= DUPLICATE_DISTANCE for other in accepted):
            dropped += 1
            continue
        kept.append(entry)
        accepted.append(entry.image_hash)
    return kept, dropped


def _write_entries(entries: Sequence[_Entry], split: str, output_dir: Path) -> int:
    """Copia las imágenes del split y escribe sus etiquetas.

    Returns:
        El número de cajas escritas.
    """
    if not entries:
        return 0
    images_dir = ensure_private_dir(output_dir / "images" / split)
    labels_dir = ensure_private_dir(output_dir / "labels" / split)
    boxes = 0
    for entry in entries:
        name = f"{entry.source}__{entry.stem}"
        shutil.copyfile(entry.image_path, images_dir / f"{name}{entry.image_path.suffix}")
        (labels_dir / f"{name}.txt").write_text(format_labels(entry.boxes), encoding="utf-8")
        boxes += len(entry.boxes)
    return boxes


def _write_data_yaml(output_dir: Path) -> None:
    """Escribe el `data.yaml` del dataset unificado, con la clase 0 `plate`."""
    data: dict[str, object] = {
        "path": str(output_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {0: PLATE_CLASS_NAME},
    }
    text = yaml.safe_dump(data, sort_keys=False)
    (output_dir / "data.yaml").write_text(text, encoding="utf-8")


def _write_provenance(entries: Sequence[_Entry], output_dir: Path, raw_root: Path) -> None:
    """Escribe el CSV de trazabilidad de las imágenes copiadas (SEG-14)."""
    base = raw_root.resolve()
    with (output_dir / "provenance.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(PROVENANCE_HEADER)
        for entry in entries:
            writer.writerow(
                [
                    entry.split,
                    f"{entry.source}__{entry.stem}{entry.image_path.suffix}",
                    entry.source,
                    str(entry.image_path.relative_to(base)),
                    hashlib.sha256(entry.image_path.read_bytes()).hexdigest(),
                ]
            )


def _require_empty(output_dir: Path) -> None:
    """Exige que el directorio de salida no exista o esté vacío.

    Raises:
        DatasetError: si la ruta existe y no es un directorio vacío.
    """
    if not output_dir.exists():
        return
    if not output_dir.is_dir() or any(output_dir.iterdir()):
        raise DatasetError("el directorio de salida no está vacío")
