"""Adaptador que obtiene un fotograma completo de un video con PyAV."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import cast

import av
import av.error
import numpy as np

from lector_placas.adapters.video.pyav_source import rotation_steps
from lector_placas.application.ports import ImageBGR
from lector_placas.domain.errors import VideoSourceError

_NO_FRAMES = "el video no tiene frames decodificables"


def _to_image(frame: av.VideoFrame, steps: int) -> ImageBGR:
    """Convierte un frame de PyAV en imagen BGR upright."""
    image = cast(ImageBGR, frame.to_ndarray(format="bgr24"))
    if steps != 0:
        image = np.ascontiguousarray(np.rot90(image, k=steps))
    return image


def _first_frame(
    container: av.container.InputContainer, stream: av.video.stream.VideoStream
) -> av.VideoFrame:
    """Decodifica el primer frame del stream, que debe tener PTS."""
    try:
        first = next(container.decode(stream))
    except (StopIteration, av.error.FFmpegError) as exc:
        raise VideoSourceError(_NO_FRAMES) from exc
    if first.pts is None:
        raise VideoSourceError(_NO_FRAMES)
    return first


def _seek_and_scan(
    container: av.container.InputContainer,
    stream: av.video.stream.VideoStream,
    first: av.VideoFrame,
    timestamp_ms: int,
) -> ImageBGR:
    """Busca `timestamp_ms` y devuelve el primer frame con timestamp `>=` o el último visto."""
    steps = rotation_steps(first.rotation)
    first_pts = cast(int, first.pts)
    stream_time_base = cast(Fraction, stream.time_base)
    last: av.VideoFrame | None = None
    try:
        container.seek(
            first_pts + int(timestamp_ms / 1000 / stream_time_base),
            backward=True,
            any_frame=False,
            stream=stream,
        )
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            time_base = frame.time_base or stream_time_base
            last = frame
            if round((frame.pts - first_pts) * time_base * 1000) >= timestamp_ms:
                return _to_image(frame, steps)
    except av.error.FFmpegError as exc:
        raise VideoSourceError("error decodificando el video") from exc
    return _to_image(last if last is not None else first, steps)


class PyAVFrameGrabber:
    """Obtiene fotogramas completos de un video, en memoria."""

    def grab(self, path: Path, timestamp_ms: int) -> ImageBGR:
        """Decodifica el fotograma de `path` en `timestamp_ms`.

        Args:
            path: ruta del video.
            timestamp_ms: instante pedido, relativo al primer frame.

        Returns:
            Imagen BGR upright.

        Raises:
            VideoSourceError: si no se puede abrir o decodificar el video.
        """
        try:
            container = av.open(str(path), mode="r")
        except (av.error.FFmpegError, OSError) as exc:
            raise VideoSourceError("no se pudo abrir el video") from exc
        try:
            if not container.streams.video:
                raise VideoSourceError("el archivo no contiene video")
            stream = container.streams.video[0]
            first = _first_frame(container, stream)
            if timestamp_ms == 0:
                return _to_image(first, rotation_steps(first.rotation))
            return _seek_and_scan(container, stream, first, timestamp_ms)
        finally:
            container.close()
