"""Adaptador de exportación del dataset de legibilidad (SEG-07, spec 055)."""

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

from lector_placas.application.ports import ImageBGR, LegibilitySample
from lector_placas.domain.errors import ExportError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

DIR_PREFIX: Final[str] = "legibility-"
ANNOTATIONS_FILE: Final[str] = "annotations.csv"
IMAGES_DIR: Final[str] = "images"
_HEADER: Final[tuple[str, ...]] = (
    "image_path",
    "label",
    "status",
    "human_reviewed",
    "video_group",
    "run_id",
    "track_id",
    "vehicle_type",
    "confidence",
    "agreement",
    "num_readings",
    "reasons",
    "crop_width",
    "crop_height",
)
_TIMESTAMP_FORMAT: Final[str] = "%Y%m%dT%H%M%SZ"


class FilesystemLegibilityExportStore:
    """Escribe recortes etiquetados por legibilidad y borra los conjuntos vencidos."""

    def __init__(self, root: Path) -> None:
        """Crea el almacén sobre el directorio indicado.

        Args:
            root: directorio donde se escriben los conjuntos; no se crea aquí.
        """
        self._root = root

    def write_samples(self, samples: Sequence[LegibilitySample], created_at: datetime) -> Path:
        """Escribe un conjunto nuevo con los recortes y su `annotations.csv`.

        Args:
            samples: muestras etiquetadas a exportar; puede ser vacío.
            created_at: fecha de creación del conjunto, en UTC.

        Returns:
            Ruta del directorio creado, con sus archivos en 0600 y directorios en 0700.

        Raises:
            ExportError: Si ya existe un conjunto con ese nombre o falla la escritura.
            UnsafePathError: Si el directorio raíz no es válido.
        """
        ensure_private_dir(self._root)
        target = self._new_target(created_at)
        ensure_private_dir(target)
        images_dir = ensure_private_dir(target / IMAGES_DIR)
        try:
            for index, sample in enumerate(samples):
                _write_image(images_dir / _image_name(index), sample.image)
            _write_annotations(target / ANNOTATIONS_FILE, samples)
        except OSError as error:
            raise ExportError(
                f"no se pudo escribir la exportación de legibilidad: {target.name}"
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


def _write_annotations(path: Path, samples: Sequence[LegibilitySample]) -> None:
    """Escribe `annotations.csv` en exclusiva con permisos 0600 y UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for index, sample in enumerate(samples):
        writer.writerow(_row(index, sample))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())


def _row(index: int, sample: LegibilitySample) -> tuple[str, ...]:
    """Compone la fila CSV de una muestra, sin texto de placa ni hash de video."""
    return (
        f"{IMAGES_DIR}/{_image_name(index)}",
        sample.label.value,
        sample.status.value,
        "1" if sample.human_reviewed else "0",
        str(sample.video_group),
        str(sample.run_id),
        str(sample.track_id),
        sample.vehicle_type.value,
        f"{sample.confidence:.4f}",
        f"{sample.agreement:.4f}",
        str(sample.num_readings),
        "|".join(reason.value for reason in sample.reasons),
        str(sample.image.shape[1]),
        str(sample.image.shape[0]),
    )
