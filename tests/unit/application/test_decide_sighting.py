from __future__ import annotations

import pytest

from lector_placas.application.ports import (
    AuditEvent,
    ReviewAction,
    ReviewDecision,
    RunStart,
    VideoInfo,
)
from lector_placas.application.review_sightings import DecideSighting
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ReviewError, SightingNotFoundError
from tests.fixtures.fakes import START, FakeClock, InMemoryPlateRepository


def _plate(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(
        text, 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
    )


def _seeded(text: str) -> tuple[InMemoryPlateRepository, FakeClock, int]:
    """Repositorio con un avistamiento sintético y su reloj fijo."""
    repository = InMemoryPlateRepository()
    run_id = repository.start_run(
        RunStart("a" * 64, "parqueadero", VideoInfo(640, 480, 0, None, None, "h264"), START)
    )
    sighting_id = repository.save_sighting(
        Sighting(run_id, 1, 0, 1000, VehicleType.CAR, _plate(text), None, START)
    )
    return repository, FakeClock(), sighting_id


def test_confirm_marks_confirmed_and_returns_record() -> None:
    repository, clock, sighting_id = _seeded("ABC123")
    updated = DecideSighting(repository, clock).execute(
        sighting_id, ReviewDecision(ReviewAction.CONFIRM)
    )
    assert updated.status is ReviewStatus.CONFIRMED
    assert updated.reviewed_at == START
    assert updated == repository.get_sighting(sighting_id)


def test_correct_sets_plate_text_and_keeps_ocr_text() -> None:
    repository, clock, sighting_id = _seeded("ABC123")
    updated = DecideSighting(repository, clock).execute(
        sighting_id, ReviewDecision(ReviewAction.CORRECT, "XYZ98K")
    )
    assert updated.plate_text == "XYZ98K"
    assert updated.ocr_text == "ABC123"
    assert updated.status is ReviewStatus.CORRECTED
    assert repository.get_sighting(sighting_id).plate_text == "XYZ98K"


def test_reject_marks_rejected() -> None:
    repository, clock, sighting_id = _seeded("ABC123")
    updated = DecideSighting(repository, clock).execute(
        sighting_id, ReviewDecision(ReviewAction.REJECT)
    )
    assert updated.status is ReviewStatus.REJECTED
    assert updated.plate_text == "ABC123"


def test_skip_and_quit_raise_review_error_without_writing() -> None:
    repository, clock, sighting_id = _seeded("ABC123")
    use_case = DecideSighting(repository, clock)
    before = repository.get_sighting(sighting_id)
    events_before = len(repository.events)
    for action in (ReviewAction.SKIP, ReviewAction.QUIT):
        with pytest.raises(ReviewError):
            use_case.execute(sighting_id, ReviewDecision(action))
    assert repository.get_sighting(sighting_id) == before
    assert len(repository.events) == events_before


def test_logs_review_audit_event_without_plate_text() -> None:
    cases = [
        (ReviewAction.CONFIRM, None, "confirmados=1 corregidos=0 rechazados=0 omitidos=0"),
        (ReviewAction.CORRECT, "XYZ98K", "confirmados=0 corregidos=1 rechazados=0 omitidos=0"),
        (ReviewAction.REJECT, None, "confirmados=0 corregidos=0 rechazados=1 omitidos=0"),
    ]
    for action, corrected, expected in cases:
        repository, clock, sighting_id = _seeded("ABC123")
        DecideSighting(repository, clock).execute(sighting_id, ReviewDecision(action, corrected))
        event, _, detail = repository.events[-1]
        assert event is AuditEvent.REVIEW
        assert detail == expected
        assert "ABC123" not in detail
        assert "XYZ98K" not in detail


def test_can_change_decision_on_rejected() -> None:
    repository, clock, sighting_id = _seeded("ABC123")
    use_case = DecideSighting(repository, clock)
    use_case.execute(sighting_id, ReviewDecision(ReviewAction.REJECT))
    updated = use_case.execute(sighting_id, ReviewDecision(ReviewAction.CONFIRM))
    assert updated.status is ReviewStatus.CONFIRMED


def test_unknown_sighting_propagates_not_found() -> None:
    repository, clock, _ = _seeded("ABC123")
    with pytest.raises(SightingNotFoundError):
        DecideSighting(repository, clock).execute(999, ReviewDecision(ReviewAction.CONFIRM))
