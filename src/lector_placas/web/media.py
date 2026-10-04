"""Servicios de medios de la web: localizar el video por hash y leer su duración."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lector_placas.application.ports import FrameGrabber, VideoSourceFactory
from lector_placas.domain.errors import VideoSourceError
from lector_placas.infrastructure.config import AppConfig
from lector_placas.infrastructure.input_validation import sha256_file

VIDEO_MEDIA_TYPES: Final[Mapping[str, str]] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}


class VideoLocator:
    """Localiza un video de los directorios permitidos a partir de su SHA-256."""

    def __init__(self, config: AppConfig) -> None:
        """Guarda la configuración y crea la caché de hashes en memoria."""
        self._config = config
        self._cache: dict[tuple[str, int, int], str] = {}
        self._lock = threading.Lock()

    def candidates(self) -> list[Path]:
        """Lista los videos de los directorios permitidos, sin recorrer subdirectorios."""
        config = self._config
        found: list[Path] = []
        for directory in config.input.allowed_dirs:
            folder = config.under_root(directory)
            if not folder.exists():
                continue
            for file in sorted(folder.iterdir()):
                if file.is_file() and file.suffix.lower() in config.input.allowed_extensions:
                    found.append(file)
        return found

    def find(self, sha256: str) -> Path | None:
        """Devuelve la ruta del video cuyo SHA-256 coincide, o `None`."""
        for path in self.candidates():
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns)
            with self._lock:
                digest = self._cache.get(key)
            if digest is None:
                digest = sha256_file(path)
                with self._lock:
                    self._cache[key] = digest
            if digest == sha256:
                return path
        return None


@dataclass(frozen=True, slots=True)
class MediaServices:
    """Servicios de medios guardados en el estado de la app."""

    locator: VideoLocator
    grabber: FrameGrabber
    sources: VideoSourceFactory


def probe_duration_ms(sources: VideoSourceFactory, path: Path) -> int | None:
    """Devuelve la duración del video en milisegundos, o `None` si no se puede abrir."""
    try:
        source = sources.open(path)
        try:
            return source.info().duration_ms
        finally:
            source.close()
    except VideoSourceError:
        return None
