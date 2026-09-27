from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from lector_placas.application.ports import ReviewAction, ReviewDecision
from lector_placas.application.review_sightings import ReviewSightings, ReviewSummary
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.gui.review_dialog import (
    CURRENT_TEXT_LABEL,
    INVALID_TEXT,
    QtReviewUI,
    ReviewDialog,
)
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository

CREATED_AT = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


def _record(
    sighting_id: int = 1,
    plate_text: str = "ABC123",
    status: ReviewStatus = ReviewStatus.UNVERIFIED,
    reasons: tuple[UnverifiedReason, ...] = (UnverifiedReason.INSUFFICIENT_READINGS,),
) -> SightingRecord:
    return SightingRecord(
        sighting_id=sighting_id,
        run_id=1,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type=VehicleType.CAR,
        ocr_text=plate_text,
        plate_text=plate_text,
        confidence=0.5,
        agreement=0.5,
        num_readings=1,
        status=status,
        reasons=reasons,
        format_ids=(),
        crop_ref=None,
        created_at=CREATED_AT,
        reviewed_at=None,
    )


def _drive(dialog: ReviewDialog, keys_fn: Callable[[], None]) -> None:
    QTimer.singleShot(0, keys_fn)


def test_confirm_reject_skip_quit_keys(qapp) -> None:
    dialog = ReviewDialog()
    cases = (
        (Qt.Key.Key_C, ReviewAction.CONFIRM),
        (Qt.Key.Key_R, ReviewAction.REJECT),
        (Qt.Key.Key_S, ReviewAction.SKIP),
        (Qt.Key.Key_Escape, ReviewAction.QUIT),
    )
    for key, expected in cases:
        _drive(dialog, lambda key=key: QTest.keyClick(dialog, key))
        decision = dialog.present(_record(), None)
        assert decision.action is expected


def test_edit_and_correct(qapp) -> None:
    dialog = ReviewDialog()

    def keys() -> None:
        QTest.keyClick(dialog, Qt.Key.Key_E)
        QTest.keyClicks(dialog, "xyz98k")
        QTest.keyClick(dialog, Qt.Key.Key_Return)

    _drive(dialog, keys)
    decision = dialog.present(_record(plate_text="ABC123"), None)
    assert decision == ReviewDecision(ReviewAction.CORRECT, "XYZ98K")


def test_enter_and_space_in_menu_do_nothing(qapp) -> None:
    dialog = ReviewDialog()

    def keys() -> None:
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        QTest.keyClick(dialog, Qt.Key.Key_Space)
        assert dialog._decision is None
        QTest.keyClick(dialog, Qt.Key.Key_C)

    _drive(dialog, keys)
    decision = dialog.present(_record(), None)
    assert decision.action is ReviewAction.CONFIRM


def test_shows_current_text_label(qapp) -> None:
    dialog = ReviewDialog()
    labels = [child.text() for child in dialog.findChildren(QLabel)]
    assert CURRENT_TEXT_LABEL in labels


def test_edit_same_text_confirms(qapp) -> None:
    dialog = ReviewDialog()

    def keys() -> None:
        QTest.keyClick(dialog, Qt.Key.Key_E)
        QTest.keyClicks(dialog, "abc123")
        QTest.keyClick(dialog, Qt.Key.Key_Return)

    _drive(dialog, keys)
    decision = dialog.present(_record(plate_text="ABC123"), None)
    assert decision == ReviewDecision(ReviewAction.CONFIRM)


def test_edit_invalid_text_stays(qapp) -> None:
    dialog = ReviewDialog()

    def keys() -> None:
        QTest.keyClick(dialog, Qt.Key.Key_E)
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        assert dialog._message_label.text() == INVALID_TEXT
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    _drive(dialog, keys)
    decision = dialog.present(_record(), None)
    assert decision.action is ReviewAction.QUIT


def test_dialog_without_crop_shows_placeholder(qapp) -> None:
    dialog = ReviewDialog()
    _drive(dialog, lambda: QTest.keyClick(dialog, Qt.Key.Key_S))
    dialog.present(_record(), None)
    assert dialog._crop_label.text() == "sin recorte"
    assert dialog._crop_label.pixmap().isNull()


def _seed_two_unverified(repository: InMemoryPlateRepository) -> None:
    for index, text in enumerate(("ABC123", "XYZ98K")):
        plate = ConsolidatedPlate(
            text=text,
            confidence=0.5,
            agreement=0.5,
            num_readings=1,
            status=ReviewStatus.UNVERIFIED,
            reasons=(UnverifiedReason.INSUFFICIENT_READINGS,),
            format_ids=(),
        )
        sighting = Sighting(
            run_id=1,
            track_id=index + 1,
            first_seen_ms=0,
            last_seen_ms=1000,
            vehicle_type=VehicleType.CAR,
            plate=plate,
            crop_ref=None,
            created_at=CREATED_AT,
        )
        repository.save_sighting(sighting)


def test_qt_review_ui_works_with_review_sightings(qapp, monkeypatch) -> None:
    repository = InMemoryPlateRepository()
    _seed_two_unverified(repository)
    keys = iter([Qt.Key.Key_C, Qt.Key.Key_R])

    def fake_exec(self: ReviewDialog) -> int:
        QTest.keyClick(self, next(keys))
        return 0

    monkeypatch.setattr(ReviewDialog, "exec", fake_exec)

    ui = QtReviewUI(None)
    use_case = ReviewSightings(repository, InMemoryCropStore(), ui, FakeClock())
    summary = use_case.execute(10, ReviewStatus.UNVERIFIED)

    assert summary == ReviewSummary(confirmed=1, corrected=0, rejected=1, skipped=0)
    statuses = {record.status for record in repository.list_sightings(None, 10, 0)}
    assert statuses == {ReviewStatus.CONFIRMED, ReviewStatus.REJECTED}
