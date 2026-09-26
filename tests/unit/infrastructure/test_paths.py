from __future__ import annotations

import stat
from pathlib import Path

import pytest

from lector_placas.domain.errors import UnsafePathError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within


def test_resolve_within_accepts_inside(tmp_path: Path) -> None:
    assert resolve_within(tmp_path, Path("a/b.txt")) == (tmp_path / "a" / "b.txt").resolve()


@pytest.mark.parametrize("candidate", [Path("../x"), Path("a/../../x"), Path("/etc/passwd")])
def test_resolve_within_rejects_escape(tmp_path: Path, candidate: Path) -> None:
    with pytest.raises(UnsafePathError):
        resolve_within(tmp_path / "base", candidate)


def test_resolve_within_rejects_symlink_escape(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_within(base, Path("link/secret"))


def test_ensure_private_dir_creates_0700(tmp_path: Path) -> None:
    target = ensure_private_dir(tmp_path / "data" / "crops")
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_ensure_private_dir_rejects_file_and_symlink(tmp_path: Path) -> None:
    file_path = tmp_path / "f"
    file_path.write_text("x")
    with pytest.raises(UnsafePathError):
        ensure_private_dir(file_path)
    link = tmp_path / "l"
    link.symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        ensure_private_dir(link)
