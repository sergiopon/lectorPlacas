"""Tests de aceptación de la parada temprana en `ProcessVideo`."""

from __future__ import annotations

from pathlib import Path

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import ReviewStatus
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
    ScriptedPlateDetector,
    ScriptedVehicleDetector,
    SingleTrackTracker,
    TwoTrackTracker,
)


def build(
    stamps: list[int],
    *,
    detector: ScriptedVehicleDetector | None = None,
    plates: FixedPlateDetector | ScriptedPlateDetector | None = None,
    reader: CyclingReader | None = None,
    tracker: SingleTrackTracker | TwoTrackTracker | None = None,
    target_fps: float = 10.0,
    min_plate_width_px: int = 20,
    max_ocr_per_frame: int = 8,
    max_readings_per_track: int = 8,
    early_stop: bool = False,
):  # type: ignore[no-untyped-def]
    source = FakeSource(stamps)
    parts = {
        "source": source,
        "tracker": tracker or SingleTrackTracker(),
        "repo": InMemoryPlateRepository(),
        "crops": InMemoryCropStore(),
        "detector": detector or ScriptedVehicleDetector(),
        "plates": plates or FixedPlateDetector(),
        "reader": reader or CyclingReader(["ABC123"]),
    }
    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(target_fps),
        parts["detector"],
        parts["plates"],
        parts["tracker"],
        parts["reader"],
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1), ConfusionMap.default()
        ),
        parts["repo"],
        parts["crops"],
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings(
        "calle_lenta",
        max_ocr_per_frame,
        min_plate_width_px,
        0.0,
        0.10,
        2000,
        max_readings_per_track,
        early_stop=early_stop,
    )
    return ProcessVideo(deps, settings), parts


def _run(texts: list[str], *, early_stop: bool):  # type: ignore[no-untyped-def]
    process, parts = build(
        [i * 100 for i in range(10)],
        reader=CyclingReader(texts),
        max_readings_per_track=3,
        early_stop=early_stop,
    )
    process.execute(Path("v.mp4"), SHA)
    return parts


def test_early_stop_after_confirmed_full_track() -> None:
    parts = _run(["ABC123"], early_stop=True)
    assert parts["reader"].calls == 3
    records = parts["repo"].list_sightings(None, 10, 0)
    assert len(records) == 1
    assert records[0].status is ReviewStatus.CONFIRMED
    assert records[0].num_readings == 3
    assert records[0].last_seen_ms == 900


def test_no_early_stop_reads_every_frame() -> None:
    parts = _run(["ABC123"], early_stop=False)
    assert parts["reader"].calls == 10


def test_unconfirmed_full_track_keeps_reading() -> None:
    parts = _run(["ABC123", "ABD123", "ABE123"], early_stop=True)
    assert parts["reader"].calls == 10
    records = parts["repo"].list_sightings(None, 10, 0)
    assert records[0].status is ReviewStatus.UNVERIFIED
