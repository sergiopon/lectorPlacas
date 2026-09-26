from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lector_placas.domain.errors import InputValidationError, UnsafePathError
from lector_placas.infrastructure.input_validation import sha256_file, validate_video_path

EXTS = frozenset({".mp4", ".mov"})


@pytest.fixture
def videos(tmp_path: Path) -> Path:
    directory = tmp_path / "videos"
    directory.mkdir()
    return directory


def make_file(path: Path, size: int = 10) -> Path:
    path.write_bytes(b"\x00" * size)
    return path


def test_valid_video_path(videos: Path) -> None:
    video = make_file(videos / "clip.MP4")
    assert validate_video_path(video, [videos], EXTS, 100) == video.resolve()


def test_rejects_missing_extension_size_and_location(tmp_path: Path, videos: Path) -> None:
    with pytest.raises(InputValidationError):
        validate_video_path(videos / "nada.mp4", [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "a.txt"), [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "big.mp4", 101), [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "empty.mp4", 0), [videos], EXTS, 100)
    with pytest.raises(UnsafePathError):
        validate_video_path(make_file(tmp_path / "out.mp4"), [videos], EXTS, 100)


def test_rejects_symlink_and_directory(tmp_path: Path, videos: Path) -> None:
    target = make_file(tmp_path / "real.mp4")
    link = videos / "link.mp4"
    link.symlink_to(target)
    with pytest.raises(InputValidationError):
        validate_video_path(link, [videos], EXTS, 100)
    folder = videos / "folder.mp4"
    folder.mkdir()
    with pytest.raises(InputValidationError):
        validate_video_path(folder, [videos], EXTS, 100)


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"lector" * 400_000)
    assert sha256_file(path) == hashlib.sha256(b"lector" * 400_000).hexdigest()
    with pytest.raises(InputValidationError):
        sha256_file(tmp_path / "missing.bin")
