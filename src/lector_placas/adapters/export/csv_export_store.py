"""Adaptador de exportación de avistamientos a CSV en `data/exports/`."""

from __future__ import annotations

import csv
import io
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from lector_placas.domain.entities import SightingRecord
from lector_placas.domain.errors import ExportError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

HEADER: Final[tuple[str, ...]] = (
    "sighting_id",
    "run_id",
    "track_id",
    "first_seen_ms",
    "last_seen_ms",
    "vehicle_type",
    "plate_text",
    "ocr_text",
    "confidence",
    "agreement",
    "num_readings",
    "status",
    "reasons",
    "format_ids",
    "created_at",
    "reviewed_at",
)
FILE_GLOB: Final[str] = "sightings-*.csv"
_FORMULA_PREFIXES: Final[tuple[str, ...]] = ("=", "+", "-", "@")
_TIMESTAMP_FORMAT: Final[str] = "%Y%m%dT%H%M%SZ"


def sanitize_cell(value: str) -> str:
    """Neutraliza las celdas que una hoja de cálculo interpretaría como fórmula.

    Args:
        value: contenido de la celda.

    Returns:
        El valor original, o prefijado con `'` si empieza por `=`, `+`, `-` o `@`.
    """
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def record_to_row(record: SightingRecord) -> list[str]:
    """Convierte un avistamiento en la fila CSV correspondiente a `HEADER`.

    Args:
        record: avistamiento persistido.

    Returns:
        Una celda por columna de `HEADER`, ya saneada, en el mismo orden.
    """
    cells = (
        str(record.sighting_id),
        str(record.run_id),
        str(record.track_id),
        str(record.first_seen_ms),
        str(record.last_seen_ms),
        record.vehicle_type.value,
        record.plate_text,
        record.ocr_text,
        f"{record.confidence:.4f}",
        f"{record.agreement:.4f}",
        str(record.num_readings),
        record.status.value,
        "|".join(reason.value for reason in record.reasons),
        "|".join(record.format_ids),
        record.created_at.isoformat(timespec="microseconds"),
        "" if record.reviewed_at is None else record.reviewed_at.isoformat(timespec="microseconds"),
    )
    return [sanitize_cell(cell) for cell in cells]


class CsvExportStore:
    """Escribe exportaciones CSV privadas y borra las vencidas."""

    def __init__(self, root: Path) -> None:
        """Crea el almacén sobre el directorio de exportaciones indicado.

        Args:
            root: directorio donde se escriben las exportaciones; no se crea aquí.
        """
        self._root = root

    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path:
        """Escribe un CSV nuevo con los avistamientos indicados.

        Args:
            records: avistamientos a exportar (puede ser vacío).
            created_at: fecha de creación de la exportación, en UTC.

        Returns:
            Ruta del archivo CSV creado con permisos 0600.

        Raises:
            ExportError: Si ya existe una exportación con ese nombre o falla la escritura.
            UnsafePathError: Si el directorio de exportaciones no es válido.
        """
        ensure_private_dir(self._root)
        stamp = created_at.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)
        path = resolve_within(self._root, Path(f"sightings-{stamp}.csv"))
        content = _render(records)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as e:
            raise ExportError("ya existe una exportación con ese nombre") from e
        except OSError as e:
            raise ExportError(f"no se pudo crear la exportación: {path.name}") from e
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except OSError as e:
            raise ExportError(f"no se pudo escribir la exportación: {path.name}") from e
        return path

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra las exportaciones anteriores al corte.

        Args:
            cutoff: fecha de corte en UTC; se borran los archivos modificados antes.

        Returns:
            Número de exportaciones borradas.

        Raises:
            ExportError: Si falla el borrado de una exportación.
        """
        if not self._root.exists():
            return 0
        limit = cutoff.timestamp()
        deleted = 0
        for path in sorted(self._root.glob(FILE_GLOB)):
            try:
                stale = path.stat().st_mtime < limit
                if stale:
                    path.unlink()
            except OSError as e:
                raise ExportError(f"no se pudo borrar la exportación: {path.name}") from e
            deleted += stale
        return deleted


def _render(records: Sequence[SightingRecord]) -> str:
    """Serializa la cabecera y las filas de los avistamientos."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for record in records:
        writer.writerow(record_to_row(record))
    return buffer.getvalue()
