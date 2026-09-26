"""Resolución segura de rutas y preparación de directorios privados."""

from __future__ import annotations

from pathlib import Path

from lector_placas.domain.errors import UnsafePathError


def resolve_within(base: Path, candidate: Path) -> Path:
    """Resuelve `candidate` comprobando que no escape del directorio `base`.

    Args:
        base: Directorio permitido.
        candidate: Ruta absoluta o relativa a resolver dentro de `base`.

    Returns:
        La ruta absoluta resuelta dentro de `base`.

    Raises:
        UnsafePathError: Si la ruta resuelta queda fuera de `base`.
    """
    base_r = base.resolve()
    target = candidate if candidate.is_absolute() else base_r / candidate
    target_r = target.resolve()
    if not target_r.is_relative_to(base_r):
        raise UnsafePathError(f"ruta fuera del directorio permitido: {candidate.name}")
    return target_r


def ensure_private_dir(path: Path) -> Path:
    """Crea (si hace falta) un directorio privado con permisos 0700.

    Args:
        path: Directorio a preparar.

    Returns:
        El mismo `path`.

    Raises:
        UnsafePathError: Si `path` es un enlace simbólico, un archivo, o no puede crearse.
    """
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise UnsafePathError(f"directorio no válido: {path.name}")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
    except OSError as e:
        raise UnsafePathError(f"no se pudo preparar el directorio: {path.name}") from e
    return path
