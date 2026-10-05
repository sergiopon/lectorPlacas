from __future__ import annotations

from collections.abc import Iterator
from itertools import cycle
from pathlib import Path

import numpy as np
import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.ports import Frame, VideoInfo
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
    ReviewStatus,
    TrackedVehicle,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import InferenceError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository
from tests.fixtures.plate_catalog import build_test_catalog

SHA = "d" * 64
CAR_BOX = BoundingBox(100, 100, 300, 250)
PLATE_IN_CROP = BoundingBox(50, 100, 150, 130)


class FakeSource:
    def __init__(self, stamps: list[int]) -> None:
        self.stamps = stamps
        self.closed = False

    def info(self) -> VideoInfo:
        return VideoInfo(640, 480, 0, 1000, 10.0, "mpeg4")

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
    def __init__(self, visible_calls: int | None = None, fail_on_call: int | None = None) -> None:
        self.visible_calls = visible_calls
        self.fail_on_call = fail_on_call
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[VehicleDetection]:
        call = self.calls
        self.calls += 1
        if call == self.fail_on_call:
            raise InferenceError("fallo sintético")
        if self.visible_calls is not None and call >= self.visible_calls:
            return []
        return [VehicleDetection(CAR_BOX, 0.9, VehicleType.CAR)]


class SingleTrackTracker:
    def __init__(self) -> None:
        self.resets = 0

    def update(self, detections, image, timestamp_ms):  # type: ignore[no-untyped-def]
        return [TrackedVehicle(0, d.box, d.confidence, d.vehicle_type) for d in detections]

    def reset(self) -> None:
        self.resets += 1


class FixedPlateDetector:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.shapes: list[tuple[int, ...]] = []

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        self.shapes.append(image.shape)
        return [PlateDetection(PLATE_IN_CROP, 0.9)] if self.found else []


class ScriptedPlateDetector:
    """Devuelve cajas de placa de ancho creciente, una por llamada (la última se repite)."""

    def __init__(self, widths: list[int]) -> None:
        self.widths = widths
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        width = self.widths[min(self.calls, len(self.widths) - 1)]
        self.calls += 1
        box = BoundingBox(50, 100, 50 + width, 130)
        return [PlateDetection(box, 0.9)]


class TwoTrackTracker:
    """Sigue siempre dos vehículos fijos: uno grande y otro pequeño (copiada de test_review_024)."""

    def update(self, detections, image, timestamp_ms):  # type: ignore[no-untyped-def]
        big = BoundingBox(100, 100, 400, 300)
        small = BoundingBox(450, 100, 550, 230)
        return [
            TrackedVehicle(1, small, 0.9, VehicleType.CAR),
            TrackedVehicle(2, big, 0.9, VehicleType.CAR),
        ]

    def reset(self) -> None:
        return None


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
    )
    return ProcessVideo(deps, settings), parts


def test_happy_path_confirms_plate() -> None:
    process, parts = build([i * 100 for i in range(10)])
    result = process.execute(Path("v.mp4"), SHA)
    stats = result.stats
    assert result.run_id == 1
    assert (stats.frames_decoded, stats.frames_processed, stats.tracks_total) == (10, 10, 1)
    assert (
        stats.sightings_confirmed,
        stats.sightings_unverified,
        stats.tracks_without_reading,
    ) == (1, 0, 0)
    assert stats.processing_ms == 20
    assert stats.video_duration_ms == 1000
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert (record.plate_text, record.status, record.num_readings) == (
        "ABC123",
        ReviewStatus.CONFIRMED,
        8,
    )
    assert (record.first_seen_ms, record.last_seen_ms) == (0, 900)
    assert parts["reader"].calls == 10
    assert parts["plates"].shapes[0] == (180, 240, 3)
    assert next(iter(parts["crops"].images.values())).shape == (30, 100, 3)
    assert parts["repo"].runs[1].succeeded is True
    assert parts["source"].closed
    assert parts["tracker"].resets == 1


def test_inactive_track_is_finalized_during_video() -> None:
    process, parts = build(
        [i * 100 for i in range(31)], detector=ScriptedVehicleDetector(visible_calls=3)
    )
    stats = process.execute(Path("v.mp4"), SHA).stats
    records = parts["repo"].list_sightings(None, 10, 0)
    assert len(records) == 1 and stats.tracks_total == 1
    assert (records[0].last_seen_ms, records[0].num_readings) == (200, 3)
    assert records[0].status is ReviewStatus.CONFIRMED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"plates": FixedPlateDetector(found=False)},
        {"min_plate_width_px": 200},
        {"reader": CyclingReader([""])},
    ],
)
def test_tracks_without_reading(kwargs: dict[str, object]) -> None:
    process, parts = build([0, 100, 200], **kwargs)  # type: ignore[arg-type]
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert (stats.tracks_total, stats.tracks_without_reading) == (1, 1)
    assert parts["repo"].list_sightings(None, 10, 0) == []


def test_disagreeing_readings_are_unverified() -> None:
    process, parts = build(
        [i * 100 for i in range(10)], reader=CyclingReader(["ABC123", "ABD123", "ABE123"])
    )
    stats = process.execute(Path("v.mp4"), SHA).stats
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert stats.sightings_unverified == 1
    assert record.status is ReviewStatus.UNVERIFIED
    assert record.plate_text == "ABC123"


def test_error_marks_run_failed_and_closes_source() -> None:
    process, parts = build(
        [i * 100 for i in range(10)], detector=ScriptedVehicleDetector(fail_on_call=3)
    )
    with pytest.raises(InferenceError):
        process.execute(Path("v.mp4"), SHA)
    assert parts["repo"].runs[1].succeeded is False
    assert parts["source"].closed
    assert parts["repo"].list_sightings(None, 10, 0) == []


def test_sampling_reduces_processed_frames() -> None:
    process, _ = build([round(i * 1000 / 30) for i in range(30)])
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert (stats.frames_decoded, stats.frames_processed) == (30, 10)


def test_later_wider_plates_replace_early_readings() -> None:
    process, parts = build(
        [i * 100 for i in range(4)],
        plates=ScriptedPlateDetector([20, 30, 40, 50]),
        reader=CyclingReader(["AAA111", "AAA111", "ABC123", "ABC123"]),
        max_readings_per_track=2,
    )
    process.execute(Path("v.mp4"), SHA)
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert record.ocr_text == "ABC123"
    assert record.num_readings == 2


def test_full_track_yields_ocr_turn_to_unfilled_track() -> None:
    process, parts = build(
        [0, 100],
        tracker=TwoTrackTracker(),
        max_ocr_per_frame=1,
        max_readings_per_track=1,
    )
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert stats.tracks_total == 2
    records = parts["repo"].list_sightings(None, 10, 0)
    assert {record.track_id for record in records} == {1, 2}
    assert all(record.num_readings == 1 for record in records)
