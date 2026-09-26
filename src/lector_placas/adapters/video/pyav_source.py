"""Adaptador de fuente de video basado en PyAV."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path
from typing import cast

import av
import av.error
import numpy as np

from lector_placas.application.ports import Frame, ImageBGR, VideoInfo
from lector_placas.domain.errors import VideoSourceError

logger = logging.getLogger(__name__)

_DEGREES_PER_STEP = 90
_STEPS_PER_TURN = 4
_MICROSECONDS_PER_MS = 1000


def rotation_steps(rotation: int) -> int:
    """Convierte grados de rotación en pasos de 90° normalizados a [0, 3].

    Args:
        rotation: rotación en grados (puede ser negativa o mayor a 360).

    Returns:
        Número de pasos de 90° en sentido antihorario, en el rango [0, 3].
    """
    return round(rotation / _DEGREES_PER_STEP) % _STEPS_PER_TURN


class PyAVVideoSourceFactory:
    """Fábrica de `PyAVVideoSource` a partir de una ruta de archivo."""

    def open(self, path: Path) -> PyAVVideoSource:
        """Abre un archivo de video y valida que contenga un stream decodificable.

        Args:
            path: ruta al archivo de video.

        Returns:
            Fuente de video lista para consultar `info()` y recorrer `frames()`.

        Raises:
            VideoSourceError: si no se puede abrir, no contiene video o no decodifica.
        """
        try:
            container = av.open(str(path), mode="r")
        except (av.error.FFmpegError, OSError) as exc:
            raise VideoSourceError(f"no se pudo abrir el video: {path.name}") from exc
        if not container.streams.video:
            container.close()
            raise VideoSourceError(f"el archivo no contiene video: {path.name}")
        return PyAVVideoSource(container, path.name)


class PyAVVideoSource:
    """Fuente de video que entrega frames BGR upright con timestamp por PTS."""

    def __init__(self, container: av.container.InputContainer, name: str) -> None:
        """Inicializa la fuente decodificando el primer frame del stream de video.

        Args:
            container: contenedor de PyAV ya abierto, con al menos un stream de video.
            name: nombre del archivo (sin ruta), usado en mensajes de error.

        Raises:
            VideoSourceError: si no hay frames decodificables o el primer frame no tiene PTS.
        """
        self._container = container
        self._name = name
        self._stream = container.streams.video[0]
        self._stream.thread_type = "AUTO"
        self._decoder = container.decode(self._stream)
        self._closed = False
        self._consumed = False

        try:
            first = next(self._decoder)
        except (av.error.FFmpegError, StopIteration) as exc:
            self.close()
            raise VideoSourceError(
                f"el video no tiene frames decodificables: {self._name}"
            ) from exc

        if first.pts is None:
            self.close()
            raise VideoSourceError(f"el video no tiene frames decodificables: {self._name}")

        self._first_frame = first
        self._first_pts = first.pts
        self._steps = rotation_steps(first.rotation)

    def info(self) -> VideoInfo:
        """Devuelve los metadatos del video, con la rotación ya reflejada en ancho/alto.

        Returns:
            `VideoInfo` con dimensiones upright, rotación, duración, fps promedio y códec.
        """
        width, height = self._first_frame.width, self._first_frame.height
        if self._steps % 2 == 1:
            width, height = height, width
        duration_ms = (
            self._container.duration // _MICROSECONDS_PER_MS
            if self._container.duration is not None
            else None
        )
        average_rate = self._stream.average_rate
        average_fps = float(average_rate) if average_rate is not None and average_rate > 0 else None
        codec = self._stream.codec_context.name
        return VideoInfo(
            width=width,
            height=height,
            rotation_deg=self._steps * _DEGREES_PER_STEP,
            duration_ms=duration_ms,
            average_fps=average_fps,
            codec=codec,
        )

    def frames(self) -> Iterator[Frame]:
        """Recorre los frames del video en orden, con rotación aplicada y timestamp por PTS.

        Solo puede consumirse una vez.

        Yields:
            Cada `Frame` decodificado, con `image` en BGR upright.

        Raises:
            VideoSourceError: si ya se consumió antes, o ante error de decodificación.
        """
        if self._consumed:
            raise VideoSourceError("frames() ya fue consumido")
        self._consumed = True
        yield from self._iter_frames()

    def _iter_frames(self) -> Iterator[Frame]:
        index = 0
        last_timestamp_ms: int | None = None
        for av_frame in self._chain_frames():
            if av_frame.pts is None:
                logger.warning("frame sin pts omitido")
                continue
            time_base = cast(Fraction, av_frame.time_base or self._stream.time_base)
            timestamp_ms = round((av_frame.pts - self._first_pts) * time_base * 1000)
            if timestamp_ms < 0 or (
                last_timestamp_ms is not None and timestamp_ms < last_timestamp_ms
            ):
                logger.debug("frame fuera de orden omitido: timestamp_ms=%s", timestamp_ms)
                continue
            image = cast(ImageBGR, av_frame.to_ndarray(format="bgr24"))
            if self._steps != 0:
                image = np.ascontiguousarray(np.rot90(image, k=self._steps))
            yield Frame(index=index, timestamp_ms=timestamp_ms, image=image)
            index += 1
            last_timestamp_ms = timestamp_ms

    def _chain_frames(self) -> Iterator[av.VideoFrame]:
        yield self._first_frame
        try:
            yield from self._decoder
        except av.error.FFmpegError as exc:
            raise VideoSourceError(f"error decodificando el video: {self._name}") from exc

    def close(self) -> None:
        """Cierra el contenedor de video. Es idempotente."""
        if not self._closed:
            self._closed = True
            self._container.close()
