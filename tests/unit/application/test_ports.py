from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from lector_placas.application.ports import (
    AuditEvent,
    CropStore,
    ExportStore,
    Frame,
    KeyProvider,
    PlateRepository,
    RecordPurge,
    ReviewAction,
    ReviewDecision,
    RunStart,
    RunStats,
    VideoInfo,
)
from lector_placas.domain.errors import InvalidEntityError
from tests.fixtures.fakes import (
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
INFO = VideoInfo(1920, 1080, 0, 10_000, 30.0, "h264")


def test_frame_properties_and_validation() -> None:
    frame = Frame(0, 0, np.zeros((4, 6, 3), dtype=np.uint8))
    assert (frame.width, frame.height) == (6, 4)
    with pytest.raises(InvalidEntityError):
        Frame(0, 0, np.zeros((4, 6), dtype=np.uint8))
    with pytest.raises(InvalidEntityError):
        Frame(0, 0, np.zeros((4, 6, 3), dtype=np.float32))
    with pytest.raises(InvalidEntityError):
        Frame(-1, 0, np.zeros((4, 6, 3), dtype=np.uint8))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0},
        {"rotation_deg": 45},
        {"duration_ms": -1},
        {"average_fps": 0.0},
        {"codec": ""},
    ],
)
def test_video_info_validation(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = dict(
        width=10, height=10, rotation_deg=0, duration_ms=None, average_fps=None, codec="h264"
    )
    values.update(kwargs)
    with pytest.raises(InvalidEntityError):
        VideoInfo(**values)  # type: ignore[arg-type]


def test_run_start_validation() -> None:
    RunStart("a" * 64, "calle_lenta", INFO, NOW)
    with pytest.raises(InvalidEntityError):
        RunStart("A" * 64, "calle_lenta", INFO, NOW)
    with pytest.raises(InvalidEntityError):
        RunStart("a" * 64, "calle_lenta", INFO, NOW.replace(tzinfo=None))


def test_run_stats_speed_factor() -> None:
    assert RunStats(1, 1, 0, 0, 0, 0, 5_000, 10_000).speed_factor == pytest.approx(2.0)
    assert RunStats(1, 1, 0, 0, 0, 0, 0, 10_000).speed_factor is None
    assert RunStats(1, 1, 0, 0, 0, 0, 10, None).speed_factor is None
    with pytest.raises(InvalidEntityError):
        RunStats(-1, 1, 0, 0, 0, 0, 10, None)


def test_record_purge_validation() -> None:
    assert RecordPurge(0, 0, 0, ()).crop_refs == ()
    with pytest.raises(InvalidEntityError):
        RecordPurge(-1, 0, 0, ())


def test_review_decision_rules() -> None:
    assert ReviewDecision(ReviewAction.CORRECT, "ABC123").corrected_text == "ABC123"
    assert ReviewDecision(ReviewAction.SKIP).corrected_text is None
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CORRECT, None)
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CORRECT, "abc")
    with pytest.raises(InvalidEntityError):
        ReviewDecision(ReviewAction.CONFIRM, "ABC123")


def test_enum_values() -> None:
    assert [e.value for e in AuditEvent] == [
        "run_started",
        "run_finished",
        "review",
        "purge",
        "export",
    ]
    assert [a.value for a in ReviewAction] == ["confirm", "correct", "reject", "skip", "quit"]


def test_fakes_satisfy_protocols() -> None:
    repository: PlateRepository = InMemoryPlateRepository()
    crops: CropStore = InMemoryCropStore()
    exports: ExportStore = InMemoryExportStore()
    keys: KeyProvider = FakeKeyProvider()
    assert repository.start_run(RunStart("a" * 64, "p", INFO, NOW)) == 1
    assert len(keys.master_key()) == 32
    assert crops.save(np.zeros((2, 2, 3), dtype=np.uint8)) == f"{1:032x}"
    assert exports.delete_older_than(NOW) == 0
