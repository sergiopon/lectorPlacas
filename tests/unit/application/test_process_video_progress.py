"""Progreso y cancelación cooperativa de `ProcessVideo`."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import cycle
from pathlib import Path

import numpy as np
import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.ports import Frame, ProgressUpdate, VideoInfo
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox,
    OcrResult,
    PlateDetection,
    TrackedVehicle,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import InvalidEntityError, ProcessingCancelledError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository
from tests.fixtures.plate_catalog import build_test_catalog

SHA = "d" * 64
FRAME_COUNT = 8
FRAME_INTERVAL_MS = 200
VIDEO_DURATION_MS = 1600
TARGET_FPS = 2.5
FINALIZE_AFTER_MS = 300
SAMPLED_STAMPS = [0, 400, 800, 1200]
TRACK_A_BOX = BoundingBox(100, 100, 300, 250)
TRACK_B_BOX = BoundingBox(350, 150, 550, 300)
PLATE_IN_CROP = BoundingBox(50, 100, 150, 130)


class FakeSource:
    def __init__(self, stamps: list[int]) -> None:
        self.stamps = stamps
        self.closed = False

    def info(self) -> VideoInfo:
        return VideoInfo(640, 480, 0, VIDEO_DURATION_MS, 10.0, "mpeg4")

    def frames(self) -> Iterator[Frame]:
        for index, stamp in enumerate(self.stamps):
            yield Frame(index, stamp, np.full((480, 640, 3), 90, np.uint8))

    def close(self) -> None:
        self.closed = True


class FakeSourceFactory:
    def __init__(self, source: FakeSource) -> None:
        self.source = source

    def open(self, path: Path) -> FakeSource:
        return self.source


class ScriptedVehicleDetector:
    """Devuelve la caja guionada para cada llamada; `None` significa que no hay vehículo."""

    def __init__(self, boxes: list[BoundingBox | None]) -> None:
        self.boxes = boxes
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[VehicleDetection]:
        index = self.calls
        self.calls += 1
        if index >= len(self.boxes) or self.boxes[index] is None:
            return []
        return [VehicleDetection(self.boxes[index], 0.9, VehicleType.CAR)]  # type: ignore[arg-type]


class RegionTracker:
    """Asigna un `track_id` estable por caja y lo reinicia con `reset`."""

    def __init__(self) -> None:
        self._ids: dict[tuple[float, float, float, float], int] = {}
        self.resets = 0

    def update(self, detections, image, timestamp_ms):  # type: ignore[no-untyped-def]
        tracked = []
        for detection in detections:
            box = detection.box
            key = (box.x1, box.y1, box.x2, box.y2)
            if key not in self._ids:
                self._ids[key] = len(self._ids)
            tracked.append(
                TrackedVehicle(self._ids[key], box, detection.confidence, detection.vehicle_type)
            )
        return tracked

    def reset(self) -> None:
        self._ids.clear()
        self.resets += 1


class FixedPlateDetector:
    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        return [PlateDetection(PLATE_IN_CROP, 0.9)]


class CyclingReader:
    def __init__(self, texts: list[str], conf: float = 0.95) -> None:
        self.texts = cycle(texts)
        self.conf = conf
        self.calls = 0

    def read(self, plate_images):  # type: ignore[no-untyped-def]
        self.calls += 1
        results = []
        for _ in plate_images:
            text = next(self.texts)
            results.append(OcrResult(text, (self.conf,) * len(text)))
        return results


class ConstantQuality:
    def sharpness(self, image: np.ndarray) -> float:
        return 50.0


class RecordingReporter:
    """Reporter de prueba: guarda los avances y cancela según lo configurado.

    `cancel_after_reports=0` cancela antes del primer frame; `None` nunca cancela.
    """

    def __init__(
        self,
        *,
        cancel_after_reports: int | None = None,
        repository: InMemoryPlateRepository | None = None,
    ) -> None:
        self.updates: list[ProgressUpdate] = []
        self.saved_at_report: list[int] = []
        self._cancel_after = cancel_after_reports
        self._repository = repository

    def report(self, update: ProgressUpdate) -> None:
        self.updates.append(update)
        if self._repository is not None:
            self.saved_at_report.append(len(self._repository.records))

    def cancel_requested(self) -> bool:
        if self._cancel_after is None:
            return False
        return len(self.updates) >= self._cancel_after


def build(
    detector: ScriptedVehicleDetector | None = None,
):  # type: ignore[no-untyped-def]
    source = FakeSource([index * FRAME_INTERVAL_MS for index in range(FRAME_COUNT)])
    parts = {
        "source": source,
        "tracker": RegionTracker(),
        "repo": InMemoryPlateRepository(),
        "crops": InMemoryCropStore(),
        "detector": detector
        or ScriptedVehicleDetector([TRACK_A_BOX, TRACK_A_BOX, TRACK_B_BOX, TRACK_B_BOX]),
        "plates": FixedPlateDetector(),
        "reader": CyclingReader(["ABC123"]),
    }
    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(TARGET_FPS),
        parts["detector"],
        parts["plates"],
        parts["tracker"],
        parts["reader"],
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(1, 0.5, 0.6, 0.1), ConfusionMap.default()
        ),
        parts["repo"],
        parts["crops"],
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings("calle_lenta", 8, 20, 0.0, 0.10, FINALIZE_AFTER_MS, 8)
    return ProcessVideo(deps, settings), parts


def test_progress_update_rejects_negative_values() -> None:
    base = {
        "frames_decoded": 1,
        "frames_processed": 1,
        "position_ms": 1,
        "duration_ms": 10,
        "sightings_saved": 1,
    }
    for field in base:
        values = dict(base)
        values[field] = -1
        with pytest.raises(InvalidEntityError) as error:
            ProgressUpdate(**values)
        assert field in str(error.value)


def test_progress_update_fraction() -> None:
    assert ProgressUpdate(0, 0, 0, None, 0).fraction is None
    assert ProgressUpdate(0, 0, 0, 0, 0).fraction is None
    assert ProgressUpdate(1, 1, 500, 1000, 0).fraction == 0.5
    assert ProgressUpdate(1, 1, 1500, 1000, 0).fraction == 1.0


def test_execute_without_progress_behaves_as_before() -> None:
    plain, parts_plain = build()
    plain_result = plain.execute(Path("v.mp4"), SHA)
    reported, parts_reported = build()
    reporter = RecordingReporter()
    reported_result = reported.execute(Path("v.mp4"), SHA, reporter)
    assert plain_result == reported_result
    assert parts_plain["repo"].records == parts_reported["repo"].records
    assert parts_plain["repo"].runs == parts_reported["repo"].runs
    assert parts_plain["repo"].plates == parts_reported["repo"].plates
    assert reporter.updates != []


def test_reports_once_per_processed_frame() -> None:
    process, _ = build()
    reporter = RecordingReporter()
    stats = process.execute(Path("v.mp4"), SHA, reporter).stats
    decoded = [update.frames_decoded for update in reporter.updates]
    processed = [update.frames_processed for update in reporter.updates]
    assert len(reporter.updates) == stats.frames_processed
    assert decoded == sorted(decoded) and len(set(decoded)) == len(decoded)
    assert processed == sorted(processed) and len(set(processed)) == len(processed)
    assert processed == [1, 2, 3, 4]
    assert [update.position_ms for update in reporter.updates] == SAMPLED_STAMPS
    assert {update.duration_ms for update in reporter.updates} == {VIDEO_DURATION_MS}


def test_sightings_saved_counts_persisted_tracks() -> None:
    process, parts = build()
    reporter = RecordingReporter(repository=parts["repo"])
    process.execute(Path("v.mp4"), SHA, reporter)
    assert reporter.updates[-1].sightings_saved == reporter.saved_at_report[-1]
    assert reporter.saved_at_report == [0, 0, 1, 1]
    assert len(parts["repo"].records) == 2
    assert parts["repo"].list_sightings(None, 10, 0) != []


def test_cancel_raises_and_marks_run_failed() -> None:
    process, parts = build()
    reporter = RecordingReporter(cancel_after_reports=2)
    with pytest.raises(ProcessingCancelledError, match="procesamiento cancelado por el operador"):
        process.execute(Path("v.mp4"), SHA, reporter)
    assert len(reporter.updates) == 2
    run = parts["repo"].runs[1]
    assert run.succeeded is False
    assert run.stats is not None
    assert run.stats.frames_decoded < FRAME_COUNT
    assert run.stats.frames_processed == 2
    assert run.stats.sightings_confirmed + run.stats.sightings_unverified == 0
    assert parts["repo"].records == {}
    assert parts["repo"].list_sightings(None, 10, 0) == []
    assert parts["source"].closed


def test_cancel_before_first_frame() -> None:
    process, parts = build()
    reporter = RecordingReporter(cancel_after_reports=0)
    with pytest.raises(ProcessingCancelledError, match="procesamiento cancelado por el operador"):
        process.execute(Path("v.mp4"), SHA, reporter)
    assert reporter.updates == []
    run = parts["repo"].runs[1]
    assert run.succeeded is False
    assert run.stats is not None
    assert run.stats.frames_processed == 0
    assert parts["repo"].records == {}
    assert parts["source"].closed
