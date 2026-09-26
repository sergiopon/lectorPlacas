"""Validación del video de entrada y cálculo del hash SHA-256 de archivos."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from lector_placas.domain.errors import InputValidationError, UnsafePathError

CHUNK_SIZE: Final[int] = 1024 * 1024


def validate_video_path(
    path: Path,
    allowed_dirs: Sequence[Path],
    allowed_extensions: frozenset[str],
    max_size_bytes: int,
) -> Path:
    """Valida que `path` sea un video legible dentro de los directorios permitidos.

    Args:
        path: Ruta del video indicada por el usuario.
        allowed_dirs: Directorios dentro de los cuales debe estar el video.
        allowed_extensions: Extensiones permitidas, en minúsculas y con punto.
        max_size_bytes: Tamaño máximo aceptado, en bytes.

    Returns:
        La ruta resuelta del video.

    Raises:
        InputValidationError: Si el video no existe, no es un archivo regular, tiene una
            extensión no permitida, está vacío o supera el tamaño máximo.
        UnsafePathError: Si el video está fuera de los directorios permitidos.
    """
    if path.is_symlink():
        raise InputValidationError("el video no puede ser un enlace simbólico")
    try:
        resolved = path.resolve(strict=True)
    except OSError as e:
        raise InputValidationError(f"el video no existe: {path.name}") from e
    if not resolved.is_file():
        raise InputValidationError("el video no es un archivo regular")
    if resolved.suffix.lower() not in allowed_extensions:
        raise InputValidationError(f"extensión no permitida: {resolved.suffix}")
    if not any(resolved.is_relative_to(d.resolve()) for d in allowed_dirs):
        raise UnsafePathError("el video está fuera de los directorios permitidos")
    size = resolved.stat().st_size
    if size == 0:
        raise InputValidationError("el video está vacío")
    if size > max_size_bytes:
        raise InputValidationError("el video supera el tamaño máximo")
    return resolved


def sha256_file(path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo leyéndolo por bloques.

    Args:
        path: Ruta del archivo a leer.

    Returns:
        El hash SHA-256 en hexadecimal minúsculas.

    Raises:
        InputValidationError: Si el archivo no puede leerse.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError as e:
        raise InputValidationError(f"no se pudo leer el archivo: {path.name}") from e
    return digest.hexdigest()
