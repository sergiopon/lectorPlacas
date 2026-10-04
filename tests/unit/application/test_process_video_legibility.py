from __future__ import annotations

from pathlib import Path

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.legibility import LegibilityModel
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
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
    SingleTrackTracker,
)


def make_model(bias: tuple[float, float, float]) -> LegibilityModel:
    return LegibilityModel((0.0,) * 16, (1.0,) * 16, ((0.0,) * 16,) * 3, bias, 0.5)


def build(legibility: LegibilityModel | None):  # type: ignore[no-untyped-def]
    source = FakeSource([i * 100 for i in range(10)])
    repo = InMemoryPlateRepository()
    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(10.0),
        ScriptedVehicleDetector(),
        FixedPlateDetector(),
        SingleTrackTracker(),
        CyclingReader(["ABC123"]),
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1), ConfusionMap.default()
        ),
        repo,
        InMemoryCropStore(),
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings("calle_lenta", 8, 20, 0.0, 0.10, 2000, 8, legibility=legibility)
    return ProcessVideo(deps, settings), repo


def test_filter_marks_confirmed_as_not_plate() -> None:
    process, repo = build(make_model((0.0, 0.0, 1.0)))
    stats = process.execute(Path("v.mp4"), SHA).stats
    record = repo.list_sightings(None, 10, 0)[0]
    assert record.status is ReviewStatus.UNVERIFIED
    assert record.reasons == (UnverifiedReason.PREDICTED_NOT_PLATE,)
    assert stats.sightings_unverified == 1


def test_filter_keeps_legible() -> None:
    process, repo = build(make_model((5.0, 0.0, 0.0)))
    process.execute(Path("v.mp4"), SHA)
    record = repo.list_sightings(None, 10, 0)[0]
    assert record.status is ReviewStatus.CONFIRMED
    assert record.reasons == ()


def test_no_model_no_change() -> None:
    process, repo = build(None)
    process.execute(Path("v.mp4"), SHA)
    assert repo.list_sightings(None, 10, 0)[0].status is ReviewStatus.CONFIRMED
