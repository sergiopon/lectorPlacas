"""Tests de aceptación del marcado de duplicados en `ProcessVideo`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.errors import InvalidEntityError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository
from tests.fixtures.plate_catalog import build_test_catalog
from tests.unit.application.test_process_video import (
    SHA,
    ConstantQuality,
    CyclingReader,
    FakeSource,
    FakeSourceFactory,
    FixedPlateDetector,
    ScriptedVehicleDetector,
    TwoTrackTracker,
)


def build(dedup_window_ms: int):  # type: ignore[no-untyped-def]
    source = FakeSource([i * 100 for i in range(10)])
    repo = InMemoryPlateRepository()
    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(10.0),
        ScriptedVehicleDetector(),
        FixedPlateDetector(),
        TwoTrackTracker(),
        CyclingReader(["ABC123"]),
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1), ConfusionMap.default()
        ),
        repo,
        InMemoryCropStore(),
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings(
        "calle_lenta", 8, 20, 0.0, 0.10, 2000, 8, dedup_window_ms=dedup_window_ms
    )
    return ProcessVideo(deps, settings), repo


def test_same_plate_two_tracks_marks_duplicate(caplog: pytest.LogCaptureFixture) -> None:
    process, repo = build(30000)
    with caplog.at_level(logging.INFO):
        process.execute(Path("v.mp4"), SHA)
    assert len(repo.records) == 2
    assert repo.records[2].duplicate_of == 1
    assert repo.records[1].duplicate_of is None
    assert "duplicados run_id=1 marcados=1" in caplog.text


def test_dedup_disabled(caplog: pytest.LogCaptureFixture) -> None:
    process, repo = build(0)
    with caplog.at_level(logging.INFO):
        process.execute(Path("v.mp4"), SHA)
    assert len(repo.records) == 2
    assert all(record.duplicate_of is None for record in repo.records.values())
    assert "duplicados" not in caplog.text


def test_invalid_dedup_window() -> None:
    for value in (600001, -1):
        with pytest.raises(InvalidEntityError):
            ProcessingSettings("calle_lenta", 8, 20, 0.0, 0.10, 2000, 8, dedup_window_ms=value)
