"""Descarga de datasets de Roboflow por su API REST (ADR-012, SEG-20/SEG-21).

Segundo módulo con red, junto a `model_fetcher.py`: solo lo usan `lector dataset download`
y `lector dataset prepare`. La clave de API se lee de la variable de entorno `ENV_API_KEY`
y NO DEBE aparecer en logs, mensajes de error ni archivos (SEG-21, SEG-25, SEG-26); por eso
ningún mensaje de este módulo incluye la URL consultada.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, Protocol, cast

from lector_placas.domain.errors import ConfigurationError, DatasetError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

API_URL: Final[str] = "https://api.roboflow.com"
ENV_API_KEY: Final[str] = "ROBOFLOW_API_KEY"
POLL_SECONDS: Final[float] = 2.0
MAX_POLLS: Final[int] = 150
TIMEOUT_SECONDS: Final[float] = 60.0
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 600.0
_LINK_PREFIX: Final[str] = "https://"
_OK: Final[int] = 200
_GENERATING: Final[int] = 202


class HttpGet(Protocol):
    """Obtiene una URL y devuelve su código de estado y su cuerpo."""

    def __call__(self, url: str, timeout: float) -> tuple[int, bytes]:
        """Consulta `url` y devuelve `(status, body)`.

        Args:
            url: URL a consultar.
            timeout: Tiempo máximo de espera, en segundos.

        Returns:
            El código de estado HTTP y el cuerpo de la respuesta.
        """
        ...


def default_http_get(url: str, timeout: float) -> tuple[int, bytes]:
    """Consulta `url` con `urllib.request` (implementación real, única con red).

    Args:
        url: URL a consultar.
        timeout: Tiempo máximo de espera, en segundos.

    Returns:
        El código de estado HTTP y el cuerpo de la respuesta.

    Raises:
        DatasetError: Si la conexión falla o expira; el mensaje no incluye la URL,
            que lleva la clave de API.
    """
    try:
        # S310: la URL sale de API_URL o del enlace de exportación validado como https.
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return int(response.status), cast(bytes, response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise DatasetError("error de red al contactar Roboflow") from error


def api_key_from_env(environ: Mapping[str, str]) -> str:
    """Lee la clave de API del entorno.

    Args:
        environ: Entorno del proceso; en producción, `os.environ`.

    Returns:
        La clave de API no vacía.

    Raises:
        ConfigurationError: Si la variable de entorno está ausente o vacía.
    """
    api_key = environ.get(ENV_API_KEY, "").strip()
    if not api_key:
        raise ConfigurationError(f"defina la variable de entorno {ENV_API_KEY}")
    return api_key


def latest_version(http_get: HttpGet, api_key: str, workspace: str, project: str) -> int:
    """Consulta el número de la última versión del proyecto.

    Args:
        http_get: Cliente HTTP inyectable; en producción, `default_http_get`.
        api_key: Clave de API de Roboflow.
        workspace: Espacio de trabajo del proyecto.
        project: Nombre del proyecto.

    Returns:
        El mayor número de versión publicado.

    Raises:
        DatasetError: Si la consulta falla o la lista de versiones no tiene el
            formato esperado.
    """
    url = f"{API_URL}/{workspace}/{project}?api_key={api_key}"
    status, body = http_get(url, TIMEOUT_SECONDS)
    if status != _OK:
        raise DatasetError(f"no se pudo consultar {workspace}/{project} (HTTP {status})")
    try:
        payload = json.loads(body.decode("utf-8"))
        versions = cast(list[Mapping[str, object]], payload["versions"])
        return max(int(str(item["id"]).rsplit("/", 1)[-1]) for item in versions)
    except (KeyError, TypeError, ValueError) as error:
        raise DatasetError(f"formato de versiones inesperado: {workspace}/{project}") from error


def export_link(  # noqa: PLR0913, PLR0917 — firma fijada por la spec 036
    http_get: HttpGet,
    api_key: str,
    workspace: str,
    project: str,
    version: int,
    fmt: str,
    sleep: Callable[[float], None],
) -> str:
    """Espera a que la exportación esté lista y devuelve su enlace de descarga.

    Args:
        http_get: Cliente HTTP inyectable; en producción, `default_http_get`.
        api_key: Clave de API de Roboflow.
        workspace: Espacio de trabajo del proyecto.
        project: Nombre del proyecto.
        version: Número de versión a exportar.
        fmt: Formato de exportación, p. ej. `yolov8`.
        sleep: Espera inyectable entre sondeos; en producción, `time.sleep`.

    Returns:
        El enlace https del zip exportado.

    Raises:
        DatasetError: Si la exportación falla, no trae un enlace https o no
            termina dentro de `MAX_POLLS` sondeos.
    """
    url = f"{API_URL}/{workspace}/{project}/{version}/{fmt}?api_key={api_key}&nocache=true"
    for _ in range(MAX_POLLS):
        status, body = http_get(url, TIMEOUT_SECONDS)
        if status == _OK:
            return _link_of(body, workspace, project)
        if status != _GENERATING:
            raise DatasetError(f"exportación falló: {workspace}/{project} (HTTP {status})")
        sleep(POLL_SECONDS)
    raise DatasetError("la exportación no terminó a tiempo")


def extract_zip(data: bytes, destination: Path) -> None:
    """Extrae un zip en `destination`, rechazando entradas que escapen del directorio.

    Args:
        data: Contenido del zip.
        destination: Directorio destino, creado con permisos privados si no existe.

    Raises:
        DatasetError: Si `data` no es un zip válido.
        UnsafePathError: Si alguna entrada del zip apunta fuera de `destination`.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise DatasetError("zip inválido") from error
    with archive:
        for name in archive.namelist():
            resolve_within(destination, Path(name))
        ensure_private_dir(destination)
        archive.extractall(destination)


def download_dataset(  # noqa: PLR0913, PLR0917 — firma fijada por la spec 036
    http_get: HttpGet,
    api_key: str,
    workspace: str,
    project: str,
    fmt: str,
    destination: Path,
    sleep: Callable[[float], None],
) -> int:
    """Descarga la última versión exportada de un proyecto y la extrae.

    Args:
        http_get: Cliente HTTP inyectable; en producción, `default_http_get`.
        api_key: Clave de API de Roboflow.
        workspace: Espacio de trabajo del proyecto.
        project: Nombre del proyecto.
        fmt: Formato de exportación, p. ej. `yolov8`.
        destination: Directorio destino del dataset.
        sleep: Espera inyectable entre sondeos; en producción, `time.sleep`.

    Returns:
        El número de versión descargado.

    Raises:
        DatasetError: Si la consulta, la exportación o la descarga fallan.
        UnsafePathError: Si el zip trae entradas fuera de `destination`.
    """
    version = latest_version(http_get, api_key, workspace, project)
    link = export_link(http_get, api_key, workspace, project, version, fmt, sleep)
    status, body = http_get(link, DOWNLOAD_TIMEOUT_SECONDS)
    if status != _OK:
        raise DatasetError(f"descarga fallida: {workspace}/{project} (HTTP {status})")
    extract_zip(body, destination)
    return version


def _link_of(body: bytes, workspace: str, project: str) -> str:
    """Extrae el enlace https del cuerpo de una exportación lista."""
    try:
        payload = json.loads(body.decode("utf-8"))
        link = payload["export"]["link"]
    except (KeyError, TypeError, ValueError) as error:
        raise DatasetError(f"exportación sin enlace: {workspace}/{project}") from error
    if not isinstance(link, str) or not link.startswith(_LINK_PREFIX):
        raise DatasetError(f"exportación sin enlace: {workspace}/{project}")
    return link
