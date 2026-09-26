"""Configuración del logging del proceso con redacción de placas (SEG-04, SEG-05).

El registro se escribe en un archivo privado 0600 y en `stderr`. Todo mensaje y toda traza de
excepción pasan por `redact_plates`, de modo que ningún texto con forma de placa llega en claro
a los logs.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Final

from lector_placas.domain.errors import ConfigurationError
from lector_placas.domain.privacy import mask_plate
from lector_placas.infrastructure.paths import ensure_private_dir

PLATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{3}[0-9]{2}[A-Z0-9]?|[0-9]{3}[A-Z]{3}"
    r"|[A-Z]{2}[0-9]{4}|[RS][0-9]{5}|T[0-9]{4})(?![A-Z0-9])"
)
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"
HANDLER_MARK: Final[str] = "_lector_placas_handler"

_LOG_FILE_MODE: Final[int] = 0o600
_ALLOWED_LEVELS: Final[frozenset[str]] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_INVALID_LEVEL_MESSAGE: Final[str] = "nivel de log no válido"


def redact_plates(text: str) -> str:
    """Enmascara cualquier texto con forma de placa presente en `text`.

    Args:
        text: Texto arbitrario (mensaje de log ya formateado o traza de excepción).

    Returns:
        El texto con cada coincidencia de `PLATE_PATTERN` sustituida por su versión enmascarada.
    """
    return PLATE_PATTERN.sub(lambda match: mask_plate(match.group(0)), text)


class PlateRedactionFilter(logging.Filter):
    """Filtro que sustituye el mensaje del registro por su versión enmascarada."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Enmascara el mensaje ya formateado del registro si contiene placas.

        Args:
            record: registro de logging a inspeccionar.

        Returns:
            Siempre `True`: el registro nunca se descarta, solo se redacta.
        """
        message = record.getMessage()
        redacted = redact_plates(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


class RedactingFormatter(logging.Formatter):
    """Formateador que enmascara las placas de la salida final, trazas incluidas."""

    def format(self, record: logging.LogRecord) -> str:
        """Formatea el registro y enmascara las placas del texto resultante.

        Args:
            record: registro de logging a formatear.

        Returns:
            El texto formateado, con las placas enmascaradas.
        """
        return redact_plates(super().format(record))


def configure_logging(level: str, log_file: Path) -> None:
    """Configura el logger raíz con salida a un archivo privado y a `stderr`.

    La llamada es idempotente: retira los handlers propios de una llamada anterior antes de
    añadir los nuevos. El archivo se crea con permisos 0600 y su directorio con 0700.

    Args:
        level: nivel de logging; uno de `DEBUG`, `INFO`, `WARNING` o `ERROR`.
        log_file: ruta del archivo de log.

    Raises:
        ConfigurationError: si `level` no es uno de los niveles admitidos.
        UnsafePathError: si el directorio del archivo no puede prepararse como privado.
    """
    if level not in _ALLOWED_LEVELS:
        raise ConfigurationError(f"{_INVALID_LEVEL_MESSAGE}: {level}")
    ensure_private_dir(log_file.parent)
    if not log_file.exists():
        descriptor = os.open(log_file, os.O_CREAT | os.O_WRONLY | os.O_APPEND, _LOG_FILE_MODE)
        os.close(descriptor)
    log_file.chmod(_LOG_FILE_MODE)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARK, False):
            root.removeHandler(handler)
    root.setLevel(level)
    for handler in (_file_handler(log_file), logging.StreamHandler(sys.stderr)):
        handler.setFormatter(RedactingFormatter(LOG_FORMAT))
        handler.addFilter(PlateRedactionFilter())
        setattr(handler, HANDLER_MARK, True)
        root.addHandler(handler)


def _file_handler(log_file: Path) -> logging.FileHandler:
    """Crea el handler de archivo en modo anexado con codificación UTF-8.

    Args:
        log_file: ruta del archivo de log.

    Returns:
        El handler de archivo.
    """
    return logging.FileHandler(log_file, encoding="utf-8")
