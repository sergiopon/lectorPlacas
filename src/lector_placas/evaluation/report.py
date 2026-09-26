"""Escritura de reportes de evaluación privados y sin placas (SEG-04, SEG-05, SEG-26)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from lector_placas.domain.errors import EvaluationError
from lector_placas.infrastructure.logging_setup import PLATE_PATTERN
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

PLATE_MESSAGE: Final[str] = "el reporte no puede contener placas"
_REPORT_MODE: Final[int] = 0o600


def write_report(reports_dir: Path, payload: Mapping[str, object], created_at: datetime) -> Path:
    """Escribe un reporte JSON privado con nombre basado en la hora de creación.

    Args:
        reports_dir: directorio de reportes; se prepara con permisos 0700.
        payload: datos del reporte; no puede contener texto con forma de placa.
        created_at: instante usado para nombrar el archivo.

    Returns:
        La ruta del reporte escrito.

    Raises:
        EvaluationError: si el contenido parece incluir placas, el archivo ya existe o
            no se puede escribir.
        UnsafePathError: si el directorio de reportes no puede prepararse como privado.
    """
    ensure_private_dir(reports_dir)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if PLATE_PATTERN.search(text) is not None:
        raise EvaluationError(PLATE_MESSAGE)
    name = f"report-{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}.json"
    target = resolve_within(reports_dir, Path(name))
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _REPORT_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise EvaluationError(f"el reporte ya existe: {target.name}") from error
    except OSError as error:
        raise EvaluationError(f"no se pudo escribir el reporte: {target.name}") from error
    return target
