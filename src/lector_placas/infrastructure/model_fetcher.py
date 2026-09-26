"""Descarga verificada de modelos: la única operación con red (ADR-012, SEG-21)."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO, Final, Protocol, cast

from lector_placas.domain.errors import ModelFetchError
from lector_placas.infrastructure.input_validation import sha256_file
from lector_placas.infrastructure.model_registry import (
    ALLOWED_PREFIX,
    ModelEntry,
    load_manifest,
)
from lector_placas.infrastructure.paths import ensure_private_dir

CHUNK_SIZE: Final[int] = 1024 * 1024
TIMEOUT_SECONDS: Final[float] = 60.0
PART_SUFFIX: Final[str] = ".part"


class UrlOpener(Protocol):
    """Abre una URL y devuelve un flujo binario legible."""

    def __call__(self, url: str, timeout: float) -> BinaryIO:
        """Devuelve el cuerpo de `url` como flujo binario.

        Args:
            url: URL a descargar.
            timeout: Tiempo máximo de espera, en segundos.

        Returns:
            Flujo binario legible con el contenido de la respuesta.
        """
        ...


def default_opener(url: str, timeout: float) -> BinaryIO:
    """Descarga `url` con `urllib.request` (implementación real, única con red).

    Args:
        url: URL a descargar; ya validada contra `ALLOWED_PREFIX`.
        timeout: Tiempo máximo de espera, en segundos.

    Returns:
        Flujo binario legible con el contenido de la respuesta.
    """
    # S310: la URL la valida `fetch_models` contra ALLOWED_PREFIX (solo https de github.com).
    return cast(BinaryIO, urllib.request.urlopen(url, timeout=timeout))  # noqa: S310


def fetch_models(manifest_path: Path, models_dir: Path, opener: UrlOpener) -> list[str]:
    """Descarga y verifica los modelos del manifiesto que tengan URL.

    Args:
        manifest_path: Ruta del manifiesto de modelos.
        models_dir: Directorio raíz donde se guardan los modelos.
        opener: Abridor de URLs inyectable; en producción, `default_opener`.

    Returns:
        Los `model_id` descargados en esta llamada, en el orden del manifiesto.

    Raises:
        ConfigurationError: Si el manifiesto no se puede leer o no valida.
        ModelFetchError: Si la URL no es de `https://github.com/`, la descarga falla o el
            tamaño o el SHA-256 no coinciden con el manifiesto.
        UnsafePathError: Si el directorio destino no puede prepararse.
    """
    manifest = load_manifest(manifest_path)
    downloaded: list[str] = []
    for entry in manifest.models:
        url = entry.url
        if url is None or _already_downloaded(models_dir, entry):
            continue
        if not url.startswith(ALLOWED_PREFIX):
            raise ModelFetchError(f"URL no permitida: {entry.model_id}")
        _download(url, entry, models_dir, opener)
        downloaded.append(entry.model_id)
    return downloaded


def _already_downloaded(models_dir: Path, entry: ModelEntry) -> bool:
    """Indica si el destino ya existe con el SHA-256 esperado."""
    path = models_dir / entry.model_id / entry.filename
    return path.is_file() and sha256_file(path) == entry.sha256


def _download(url: str, entry: ModelEntry, models_dir: Path, opener: UrlOpener) -> None:
    """Descarga, verifica y mueve el archivo de `entry` a su destino definitivo."""
    directory = ensure_private_dir(models_dir / entry.model_id)
    destination = directory / entry.filename
    partial = destination.with_name(destination.name + PART_SUFFIX)
    digest = hashlib.sha256()
    size = 0
    try:
        with opener(url, TIMEOUT_SECONDS) as source, partial.open("wb") as handle:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
                handle.write(chunk)
    except (OSError, urllib.error.URLError) as error:
        partial.unlink(missing_ok=True)
        raise ModelFetchError(f"descarga fallida: {entry.model_id}") from error
    if size != entry.size_bytes or digest.hexdigest() != entry.sha256:
        partial.unlink(missing_ok=True)
        raise ModelFetchError(f"verificación fallida: {entry.model_id}")
    partial.replace(destination)
