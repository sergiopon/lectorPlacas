from __future__ import annotations

from pathlib import Path

import av
import numpy as np
import pytest

from lector_placas.adapters.video.pyav_frame_grabber import PyAVFrameGrabber
from lector_placas.domain.errors import VideoSourceError


def make_video(path: Path) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for index in range(30):
            image = np.full((48, 64, 3), index * 8, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def test_grab_first_and_middle_frame(tmp_path: Path) -> None:
    video = make_video(tmp_path / "v.mp4")
    first = PyAVFrameGrabber().grab(video, 0)
    assert first.shape == (48, 64, 3)
    assert abs(int(first[24, 32, 0]) - 0) <= 4
    middle = PyAVFrameGrabber().grab(video, 1500)
    assert middle.shape == (48, 64, 3)
    assert abs(int(middle[24, 32, 0]) - 15 * 8) <= 4


def test_grab_past_end_returns_last(tmp_path: Path) -> None:
    video = make_video(tmp_path / "v.mp4")
    last = PyAVFrameGrabber().grab(video, 60_000)
    assert abs(int(last[24, 32, 0]) - 29 * 8) <= 4


def test_grab_errors(tmp_path: Path) -> None:
    bad = tmp_path / "secreto.mp4"
    bad.write_bytes(np.random.default_rng(0).bytes(2048))
    with pytest.raises(VideoSourceError) as info:
        PyAVFrameGrabber().grab(bad, 0)
    assert str(info.value) in {"no se pudo abrir el video", "el archivo no contiene video"}
    assert "secreto" not in str(info.value)
