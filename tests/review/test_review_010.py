"""Tests de aceptación adicionales.

Cubren casos borde que la spec no enumera explícitamente: un video con un único frame
(no debe duplicarse por el frame predecodificado en el constructor) y el cierre antes de
consumir los frames (idempotente, sin errores).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration


def test_single_frame_video_yields_exactly_one_frame(tmp_path: Path) -> None:
    """Un video de un frame entrega un único frame (el predecodificado no se repite)."""
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "one.mp4", frames=1))
    try:
        frames = list(source.frames())
    finally:
        source.close()
    assert len(frames) == 1
    assert frames[0].index == 0
    assert frames[0].timestamp_ms == 0


def test_close_before_consuming_frames_is_idempotent(tmp_path: Path) -> None:
    """Cerrar antes de consumir los frames no falla y es idempotente."""
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=3))
    source.close()
    source.close()
    source.close()
