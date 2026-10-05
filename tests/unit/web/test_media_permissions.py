from __future__ import annotations

import os
from pathlib import Path

import pytest

from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.media import VideoLocator, unreadable_video_dirs


def make_config(config: AppConfig, tmp_path: Path) -> AppConfig:
    if os.geteuid() == 0:
        pytest.skip("root ignora los permisos")
    (tmp_path / "videos").mkdir()
    return config.model_copy(update={"root_dir": tmp_path})


def test_candidates_skip_unreadable_dir(config: AppConfig, tmp_path: Path) -> None:
    cfg = make_config(config, tmp_path)
    folder = tmp_path / "videos"
    (folder / "a.mp4").write_bytes(b"x")
    folder.chmod(0o000)
    try:
        assert VideoLocator(cfg).candidates() == []
        assert unreadable_video_dirs(cfg) == ["videos"]
    finally:
        folder.chmod(0o700)


def test_candidates_skip_unreadable_file(config: AppConfig, tmp_path: Path) -> None:
    cfg = make_config(config, tmp_path)
    folder = tmp_path / "videos"
    good = folder / "a.mp4"
    bad = folder / "b.mp4"
    good.write_bytes(b"x")
    bad.write_bytes(b"x")
    good.chmod(0o644)
    bad.chmod(0o000)
    try:
        assert VideoLocator(cfg).candidates() == [good]
        assert unreadable_video_dirs(cfg) == ["videos"]
    finally:
        bad.chmod(0o700)
        folder.chmod(0o700)


def test_readable_videos_no_warning(config: AppConfig, tmp_path: Path) -> None:
    cfg = make_config(config, tmp_path)
    folder = tmp_path / "videos"
    video = folder / "a.mp4"
    video.write_bytes(b"x")
    video.chmod(0o644)
    try:
        assert unreadable_video_dirs(cfg) == []
        video.unlink()
        folder.rmdir()
        assert unreadable_video_dirs(cfg) == []
    finally:
        tmp_path.chmod(0o700)
