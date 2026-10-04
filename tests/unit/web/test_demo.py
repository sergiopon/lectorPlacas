from __future__ import annotations

import random
import re
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from lector_placas.application.ports import ProgressUpdate
from lector_placas.cli import composition
from lector_placas.domain.entities import ReviewStatus, VehicleType
from lector_placas.domain.errors import ProcessingCancelledError
from lector_placas.infrastructure.config import AppConfig, load_config
from lector_placas.web.demo import (
    DEMO_VIDEOS,
    PLATE_BGR,
    DemoKeyProvider,
    create_demo_root,
    demo_config,
    demo_runner,
    plate_text,
    render_plate,
    seed_demo,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def demo_root() -> Iterator[Path]:
    root = create_demo_root()
    yield root
    shutil.rmtree(root, ignore_errors=True)


def make_config(root: Path) -> AppConfig:
    return demo_config(load_config(ROOT / "config" / "lector.yaml"), root)


def test_render_plate() -> None:
    image = render_plate("ABC123")
    assert image.shape == (100, 300, 3)
    assert image.dtype == np.uint8
    assert tuple(int(v) for v in image[10, 150]) == PLATE_BGR
    band = image[30:71, 40:261]
    assert bool(np.any(np.all(band == (0, 0, 0), axis=2)))


def test_plate_text_formats() -> None:
    rng = random.Random(1)
    cars = [plate_text(rng, VehicleType.CAR) for _ in range(50)]
    motos = [plate_text(rng, VehicleType.MOTORCYCLE) for _ in range(50)]
    assert all(re.fullmatch(r"[A-Z]{3}[0-9]{3}", text) for text in cars)
    assert all(re.fullmatch(r"[A-Z]{3}[0-9]{2}[A-Z]", text) for text in motos)
    assert not any(c in text for text in cars + motos for c in "IOQ")


def test_create_demo_root() -> None:
    root = create_demo_root()
    try:
        assert root.is_dir()
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        for name in DEMO_VIDEOS:
            video = root / "videos" / name
            assert video.stat().st_size == 18
            assert stat.S_IMODE(video.stat().st_mode) == 0o600
    finally:
        shutil.rmtree(root)


def read_all(config: AppConfig, keys: DemoKeyProvider) -> list[tuple[str, str]]:
    repository = composition.build_repository(config, keys)
    try:
        records = repository.list_sightings(None, 100, 0)
        crop_store = composition.build_crop_store(config, keys)
        assert len(records) == 42
        for record in records:
            assert record.crop_ref is not None
            assert crop_store.load(record.crop_ref).shape == (100, 300, 3)
            assert record.quality is not None
        return [(record.plate_text, record.status.value) for record in records]
    finally:
        repository.close()


def check_counts(config: AppConfig, keys: DemoKeyProvider) -> None:
    repository = composition.build_repository(config, keys)
    try:
        records = repository.list_sightings(None, 100, 0)
        assert len(repository.run_video_hashes()) == 5
        assert sum(1 for r in records if r.duplicate_of is not None) == 2
        counts = {status: sum(1 for r in records if r.status is status) for status in ReviewStatus}
    finally:
        repository.close()
    assert counts[ReviewStatus.UNVERIFIED] == 17
    assert counts[ReviewStatus.CONFIRMED] == 10
    assert counts[ReviewStatus.CORRECTED] == 5
    assert counts[ReviewStatus.REJECTED] == 5
    assert counts[ReviewStatus.ILLEGIBLE] == 5


def check_deterministic(first: list[tuple[str, str]]) -> None:
    other_root = create_demo_root()
    try:
        other_keys = DemoKeyProvider()
        other = make_config(other_root)
        seed_demo(other, other_keys)
        assert read_all(other, other_keys) == first
    finally:
        shutil.rmtree(other_root, ignore_errors=True)


def test_seed_demo_contents(demo_root: Path) -> None:
    keys = DemoKeyProvider()
    config = make_config(demo_root)
    seed_demo(config, keys)
    check_counts(config, keys)
    check_deterministic(read_all(config, keys))


class Recorder:
    def __init__(self, cancel: bool) -> None:
        self.cancel = cancel
        self.updates: list[ProgressUpdate] = []

    def report(self, update: ProgressUpdate) -> None:
        self.updates.append(update)

    def cancel_requested(self) -> bool:
        return self.cancel


def test_demo_runner_progress_and_cancel(demo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lector_placas.web.demo.time.sleep", lambda _seconds: None)
    keys = DemoKeyProvider()
    config = make_config(demo_root)
    seed_demo(config, keys)
    runner = demo_runner(config, keys)
    video = demo_root / "videos" / DEMO_VIDEOS[0]
    reporter = Recorder(cancel=False)
    assert runner(video, "parqueadero", reporter) == 6
    assert len(reporter.updates) == 20
    cancelled = Recorder(cancel=True)
    with pytest.raises(ProcessingCancelledError):
        runner(video, "parqueadero", cancelled)
    assert cancelled.updates == []
