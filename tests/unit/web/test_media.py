from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import av
import numpy as np

from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory
from lector_placas.infrastructure.config import AppConfig
from lector_placas.infrastructure.input_validation import sha256_file
from lector_placas.web.media import VideoLocator, probe_duration_ms


def make_video(path: Path, offset: int = 0) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for index in range(30):
            image = np.full((48, 64, 3), index * 8 + offset, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def test_locator_finds_by_hash_and_caches(config: AppConfig, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    make_video(folder / "a.mp4", 0)
    second = make_video(folder / "b.mp4", 3)
    sha = hashlib.sha256(second.read_bytes()).hexdigest()
    locator = VideoLocator(config.model_copy(update={"root_dir": tmp_path}))
    assert locator.find(sha) == second
    with patch("lector_placas.web.media.sha256_file", side_effect=sha256_file) as spy:
        assert locator.find(sha) == second
        assert spy.call_count == 0
        assert locator.find("0" * 64) is None
        assert spy.call_count == 0


def test_locator_ignores_other_extensions_and_subdirs(config: AppConfig, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_bytes(b"x")
    make_video(folder / "sub" / "c.mp4")
    locator = VideoLocator(config.model_copy(update={"root_dir": tmp_path}))
    assert locator.candidates() == []


def test_probe_duration(tmp_path: Path) -> None:
    video = make_video(tmp_path / "v.mp4")
    fake = tmp_path / "x.mp4"
    fake.write_bytes(b"no es video")
    duration = probe_duration_ms(PyAVVideoSourceFactory(), video)
    assert duration is not None
    assert abs(duration - 3000) <= 100
    assert probe_duration_ms(PyAVVideoSourceFactory(), fake) is None
