from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory, rotation_steps
from lector_placas.domain.errors import VideoSourceError
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "rotation,steps", [(0, 0), (90, 1), (-90, 3), (180, 2), (-180, 2), (270, 3)]
)
def test_rotation_steps(rotation: int, steps: int) -> None:
    assert rotation_steps(rotation) == steps


def test_reads_frames_with_pts_timestamps(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=10, fps=10))
    try:
        info = source.info()
        frames = list(source.frames())
    finally:
        source.close()
    assert (info.width, info.height, info.rotation_deg, info.codec) == (64, 48, 0, "mpeg4")
    assert [f.timestamp_ms for f in frames] == [i * 100 for i in range(10)]
    assert [f.index for f in frames] == list(range(10))
    assert frames[0].image.shape == (48, 64, 3)
    assert frames[0].image[:6, :6].mean() > 200


def test_applies_display_rotation(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "r.mp4", rotation=90))
    try:
        info = source.info()
        first = next(iter(source.frames()))
    finally:
        source.close()
    assert info.rotation_deg == 90
    assert (info.width, info.height) == (48, 64)
    assert first.image.shape == (64, 48, 3)
    assert first.image.flags["C_CONTIGUOUS"]
    assert first.image[-6:, :6].mean() > 200  # np.rot90 lleva arriba-izquierda a abajo-izquierda


def test_frames_can_only_be_consumed_once(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=2))
    list(source.frames())
    with pytest.raises(VideoSourceError):
        list(source.frames())
    source.close()
    source.close()


def test_rejects_non_video(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"esto no es un video")
    with pytest.raises(VideoSourceError):
        PyAVVideoSourceFactory().open(fake)


def test_images_are_uint8_bgr(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=1))
    frame = next(iter(source.frames()))
    source.close()
    assert frame.image.dtype == np.uint8
