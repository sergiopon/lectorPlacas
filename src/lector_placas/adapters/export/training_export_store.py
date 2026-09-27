"""Adaptador de exportación de recortes revisados para reentrenar el OCR (SEG-07)."""

from __future__ import annotations

import csv
import io
import os
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import cv2

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import PLATE_TEXT_REGEX
from lector_placas.domain.errors import ExportError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

DIR_PREFIX: Final[str] = "reviewed-"
ANNOTATIONS_FILE: Final[str] = "annotations.csv"
IMAGES_DIR: Final[str] = "images"
_HEADER: Final[tuple[str, ...]] = ("image_path", "plate_text")
_TIMESTAMP_FORMAT: Final[str] = "%Y%m%dT%H%M%SZ"


class FilesystemTrainingExportStore:
    """Escribe recortes etiquetados privados y borra los conjuntos vencidos."""

    def __init__(self, root: Path) -> None:
        """Crea el almacén sobre el directorio indicado.

        Args:
            root: directorio donde se escriben los conjuntos; no se crea aquí.
        """
        self._root = root

    def write_samples(self, samples: Sequence[tuple[str, ImageBGR]], created_at: datetime) -> Path:
        """Escribe un conjunto nuevo con los recortes y su `annotations.csv`.

        Args:
            samples: pares (texto de placa, recorte BGR) a exportar; puede ser vacío.
            created_at: fecha de creación del conjunto, en UTC.

        Returns:
            Ruta del directorio creado, con sus archivos en 0600 y directorios en 0700.

        Raises:
            ExportError: Si un texto no cumple el formato de placa, ya existe un conjunto
                con ese nombre o falla la escritura.
            UnsafePathError: Si el directorio raíz no es válido.
        """
        _validate_samples(samples)
        ensure_private_dir(self._root)
        target = self._new_target(created_at)
        ensure_private_dir(target)
        images_dir = ensure_private_dir(target / IMAGES_DIR)
        try:
            for index, (_, image) in enumerate(samples):
                _write_image(images_dir / _image_name(index), image)
            _write_annotations(target / ANNOTATIONS_FILE, samples)
        except OSError as error:
            raise ExportError(
                f"no se pudo escribir la exportación de entrenamiento: {target.name}"
            ) from error
        return target

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra los conjuntos anteriores al corte.

        Args:
            cutoff: fecha de corte en UTC; se borran los conjuntos modificados antes.

        Returns:
            Número de conjuntos borrados.

        Raises:
            ExportError: Si falla el borrado de un conjunto.
        """
        if not self._root.exists():
            return 0
        limit = cutoff.timestamp()
        deleted = 0
        for path in sorted(self._root.glob(f"{DIR_PREFIX}*")):
            try:
                stale = path.stat().st_mtime < limit
                if stale:
                    shutil.rmtree(path)
            except OSError as error:
                raise ExportError(f"no se pudo borrar la exportación: {path.name}") from error
            deleted += stale
        return deleted

    def _new_target(self, created_at: datetime) -> Path:
        """Resuelve la ruta del conjunto nuevo y rechaza un nombre ya existente."""
        stamp = created_at.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)
        target = resolve_within(self._root, Path(f"{DIR_PREFIX}{stamp}"))
        if target.exists():
            raise ExportError("ya existe una exportación con ese nombre")
        return target


def _validate_samples(samples: Sequence[tuple[str, ImageBGR]]) -> None:
    """Exige que cada texto de placa cumpla `PLATE_TEXT_REGEX`.

    Raises:
        ExportError: Si algún texto no cumple el formato de placa.
    """
    for text, _ in samples:
        if PLATE_TEXT_REGEX.fullmatch(text) is None:
            raise ExportError("texto de placa inválido")


def _image_name(index: int) -> str:
    """Nombre del PNG de la muestra `index` dentro de `images/`."""
    return f"{index:06d}.png"


def _write_image(path: Path, image: ImageBGR) -> None:
    """Codifica la imagen como PNG y la escribe en exclusiva con permisos 0600.

    Raises:
        ExportError: Si OpenCV no puede codificar el recorte.
    """
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ExportError(f"no se pudo codificar el recorte: {path.name}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded.tobytes())


def _write_annotations(path: Path, samples: Sequence[tuple[str, ImageBGR]]) -> None:
    """Escribe `annotations.csv` en exclusiva con permisos 0600 y UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for index, (text, _) in enumerate(samples):
        writer.writerow((f"{IMAGES_DIR}/{_image_name(index)}", text))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())
