from __future__ import annotations

from datetime import UTC, datetime

from lector_placas.adapters.review.opencv_review_ui import OpenCvReviewUI
from lector_placas.application.ports import ReviewAction
from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType

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
    (),
    (),
    None,
    datetime(2026, 9, 24, tzinfo=UTC),
    None,
)


def ui(answers: list[str]) -> tuple[OpenCvReviewUI, list[str]]:
    output: list[str] = []
    queue = list(answers)

    def read_line(prompt: str) -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    return OpenCvReviewUI(read_line=read_line, write=output.append, show=False), output


def test_confirm_and_invalid_option() -> None:
    review, output = ui(["x", "C"])
    assert review.ask(RECORD, None).action is ReviewAction.CONFIRM
    assert "opción inválida\n" in output
    assert output[0].startswith("#1 lectura=ABC123")


def test_correct_with_validation() -> None:
    review, output = ui(["e", "abc-1", "abc128"])
    decision = review.ask(RECORD, None)
    assert (decision.action, decision.corrected_text) == (ReviewAction.CORRECT, "ABC128")
    assert "texto inválido\n" in output


def test_empty_correction_returns_to_menu() -> None:
    review, _ = ui(["e", "", "r"])
    assert review.ask(RECORD, None).action is ReviewAction.REJECT


def test_eof_quits() -> None:
    review, _ = ui([])
    assert review.ask(RECORD, None).action is ReviewAction.QUIT
    review.close()
