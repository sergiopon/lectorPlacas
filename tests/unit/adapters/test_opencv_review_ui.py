from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from lector_placas.adapters.review.opencv_review_ui import (
    BACKGROUND,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CROP_AREA_HEIGHT,
    MARGIN,
    OpenCvReviewUI,
    ReviewView,
    render_review_frame,
)
from lector_placas.application.ports import ReviewAction
from lector_placas.domain.entities import (
    ReviewStatus,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)

RECORD = SightingRecord(
    1,
    1,
    0,
    0,
    1,
    VehicleType.CAR,
    "ABC123",
    "ABC123",
    0.5,
    0.5,
    2,
    ReviewStatus.UNVERIFIED,
    (UnverifiedReason.LOW_CONFIDENCE,),
    (),
    None,
    datetime(2026, 9, 26, tzinfo=UTC),
    None,
)


class FakeWindow:
    def __init__(self, keys: list[int], open_frames: int | None = None) -> None:
        self.keys = list(keys)
        self.frames: list[np.ndarray] = []
        self.open_frames = open_frames
        self.closed = False

    def show(self, image: np.ndarray) -> None:
        self.frames.append(image)

    def wait_key(self, delay_ms: int) -> int:
        if not self.keys:
            raise AssertionError("teclas agotadas")
        return self.keys.pop(0)

    def is_open(self) -> bool:
        return self.open_frames is None or len(self.frames) < self.open_frames

    def close(self) -> None:
        self.closed = True


def ask(keys: list[int], crop: np.ndarray | None = None):  # type: ignore[no-untyped-def]
    window = FakeWindow(keys)
    decision = OpenCvReviewUI(window=window).ask(RECORD, crop)
    return decision, window


def test_idle_polling_keeps_window_alive_then_confirms() -> None:
    decision, window = ask([-1, -1, ord("c")])
    assert decision.action is ReviewAction.CONFIRM
    assert len(window.frames) == 3
    assert window.frames[0].shape == (CANVAS_HEIGHT, CANVAS_WIDTH, 3)
    assert window.frames[0].dtype == np.uint8


@pytest.mark.parametrize(
    "key,action",
    [
        (ord("R"), ReviewAction.REJECT),
        (ord("s"), ReviewAction.SKIP),
        (ord("q"), ReviewAction.QUIT),
        (27, ReviewAction.QUIT),
    ],
)
def test_menu_keys(key: int, action: ReviewAction) -> None:
    assert ask([key])[0].action is action


def test_invalid_menu_key_is_ignored() -> None:
    decision, window = ask([ord("x"), ord("c")])
    assert decision.action is ReviewAction.CONFIRM
    assert len(window.frames) == 2


def test_edit_types_uppercase_and_saves() -> None:
    keys = [ord("e"), ord("a"), ord("b"), ord("c"), ord("1"), ord("2"), ord("8"), 13]
    decision, _ = ask(keys)
    assert (decision.action, decision.corrected_text) == (ReviewAction.CORRECT, "ABC128")


def test_edit_backspace_ignores_symbols_and_limits_length() -> None:
    keys = [ord("e"), ord("a"), ord("b"), 8, ord("-"), ord("c"), 13]
    assert ask(keys)[0].corrected_text == "AC"
    long_keys = [ord("e"), *[ord("1")] * 12, 10]
    assert ask(long_keys)[0].corrected_text == "1" * 10


def test_empty_correction_is_rejected_then_fixed() -> None:
    keys = [ord("e"), 13, ord("x"), ord("y"), ord("z"), ord("9"), ord("9"), ord("9"), 13]
    assert ask(keys)[0].corrected_text == "XYZ999"


def test_escape_in_edit_returns_to_menu() -> None:
    assert ask([ord("e"), ord("a"), 27, ord("s")])[0].action is ReviewAction.SKIP


def test_closed_window_quits_without_drawing() -> None:
    window = FakeWindow([], open_frames=0)
    assert OpenCvReviewUI(window=window).ask(RECORD, None).action is ReviewAction.QUIT
    assert window.frames == []


def test_nothing_is_written_to_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    ask([ord("e"), ord("a"), 13])
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_close_delegates_to_window() -> None:
    window = FakeWindow([])
    OpenCvReviewUI(window=window).close()
    assert window.closed


def test_render_places_crop_in_center_of_area() -> None:
    crop = np.zeros((20, 60, 3), np.uint8)
    crop[:, :] = (0, 0, 255)
    frame = render_review_frame(ReviewView(RECORD, crop, None, None))
    center_y = MARGIN + CROP_AREA_HEIGHT // 2
    assert frame[center_y, CANVAS_WIDTH // 2].tolist() == [0, 0, 255]
    assert frame[2, 2].tolist() == list(BACKGROUND)


def test_render_without_crop_and_in_edit_mode() -> None:
    frame = render_review_frame(ReviewView(RECORD, None, "AB", "texto invalido"))
    assert frame.shape == (CANVAS_HEIGHT, CANVAS_WIDTH, 3)
    assert frame[2, 2].tolist() == list(BACKGROUND)
