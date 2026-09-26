"""Lectura del CSV `image_path,plate_text` de recortes de OCR (docs/04-evaluacion.md §2)."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from lector_placas.domain.entities import PLATE_TEXT_REGEX
from lector_placas.domain.errors import EvaluationError
from lector_placas.infrastructure.paths import resolve_within

REQUIRED_COLUMNS: Final[tuple[str, ...]] = ("image_path", "plate_text")


def read_ocr_annotations(csv_path: Path) -> list[tuple[Path, str]]:
    """Lee las anotaciones de recortes de OCR de un CSV.

    Args:
        csv_path: ruta del CSV con columnas `image_path` y `plate_text`.

    Returns:
        Pares (ruta de imagen resuelta, texto de placa), en el orden del CSV.

    Raises:
        EvaluationError: si faltan columnas, el archivo no se puede leer, hay filas sin
            texto válido o el CSV no tiene filas.
        UnsafePathError: si alguna imagen queda fuera del directorio del CSV.
    """
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require_columns(reader.fieldnames or [])
            rows = [_row(csv_path, row) for row in reader]
    except OSError as error:
        raise EvaluationError(f"no se pudo leer el CSV: {csv_path.name}") from error
    if not rows:
        raise EvaluationError("el CSV no tiene filas")
    return rows


def _require_columns(fieldnames: Sequence[str]) -> None:
    """Exige que el CSV declare todas las columnas requeridas."""
    missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
    if missing:
        raise EvaluationError(f"faltan columnas en el CSV: {', '.join(missing)}")


def _row(csv_path: Path, row: Mapping[str, str | None]) -> tuple[Path, str]:
    """Valida el texto de placa de una fila y resuelve su ruta de imagen."""
    text = row.get("plate_text") or ""
    if PLATE_TEXT_REGEX.fullmatch(text) is None:
        raise EvaluationError("texto de placa inválido en una fila del CSV")
    raw_path = row.get("image_path") or ""
    return resolve_within(csv_path.parent, Path(raw_path)), text
