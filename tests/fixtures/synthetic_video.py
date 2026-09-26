from __future__ import annotations

from pathlib import Path

import av
import numpy as np


def synthetic_frame(index: int, width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:8, :8] = 255  # marca blanca arriba a la izquierda
    image[height - 4 :, :, 2] = (index * 20) % 256
    return image


def write_video(
    path: Path,
    frames: int = 10,
    fps: int = 10,
    width: int = 64,
    height: int = 48,
    rotation: float | None = None,
) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        if rotation is not None:
            stream.set_display_rotation(rotation)
        for index in range(frames):
            frame = av.VideoFrame.from_ndarray(
                synthetic_frame(index, width, height), format="bgr24"
            )
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path
