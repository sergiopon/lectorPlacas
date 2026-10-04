from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import RunStart, VideoInfo
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, None, None, "h264")


def open_repo(tmp_path: Path) -> SqlCipherPlateRepository:
    return SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider())


def test_returns_hash_per_run(tmp_path: Path) -> None:
    repo = open_repo(tmp_path)
    assert repo.run_video_hashes() == {}
    first = repo.start_run(RunStart("a" * 64, "p", INFO, T0))
    second = repo.start_run(RunStart("b" * 64, "p", INFO, T0))
    assert repo.run_video_hashes() == {first: "a" * 64, second: "b" * 64}
    repo.close()
