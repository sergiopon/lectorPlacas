from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from lector_placas.application.ports import ReviewAction, ReviewDecision
from lector_placas.domain.entities import (
    ReviewStatus,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.gui.labels import REASON_TEXTS
from lector_placas.gui.review_panel import ReviewPanel

CREATED_AT = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
INVALID_MESSAGE = "Escribe solo letras y números (1 a 10)"
BUSY_MESSAGE = "Espera a que termine el procesamiento para revisar."


def _record(
    plate_text: str = "ABC123",
    ocr_text: str | None = None,
    reasons: tuple[UnverifiedReason, ...] = (),
    run_id: int = 1,
) -> SightingRecord:
    return SightingRecord(
        sighting_id=1,
        run_id=run_id,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=65_000,
        vehicle_type=VehicleType.CAR,
        ocr_text=plate_text if ocr_text is None else ocr_text,
        plate_text=plate_text,
        confidence=0.873,
        agreement=0.5,
        num_readings=3,
        status=ReviewStatus.UNVERIFIED,
        reasons=reasons,
        format_ids=(),
        crop_ref=None,
        created_at=CREATED_AT,
        reviewed_at=None,
    )


@pytest.fixture
def shown_panel(qapp):
    """Entrega un panel visible y lo cierra al terminar (una ventana abierta bloquea el próximo modal)."""
    panel = ReviewPanel()
    panel.show()
    qapp.processEvents()
    yield panel
    panel.close()


def test_empty_panel_shows_hint(qapp) -> None:
    panel = ReviewPanel()
    assert panel._stack.currentWidget() is panel._empty
    assert panel._empty._title_label.text() == "Elige una placa"
    assert (
        panel._empty._hint_label.text()
        == "Haz clic en una tarjeta para verla en grande y revisarla."
    )


def _assert_full_record(panel: ReviewPanel, reasons: tuple[UnverifiedReason, ...]) -> None:
    assert panel._plate_label.text() == "ABC 123"
    assert panel._plate_label.objectName() == "PlateText"
    assert panel._status_label.text() == "Por revisar"
    assert panel._crop_label.text() == "sin imagen"
    assert (panel._confidence_bar.value(), panel._confidence_bar.format()) == (87, "87 %")
    assert panel._ocr_label.isVisible() is True
    assert panel._ocr_label.text() == "El sistema leyó: ABD 123"
    assert panel._reasons_title.isVisible() is True
    expected = "\n".join(f"• {REASON_TEXTS[reason]}" for reason in reasons)
    assert panel._reasons_label.text() == expected
    assert len(panel._reasons_label.text().splitlines()) == len(reasons)
    assert "video 1" in panel._meta_label.text()
    assert "0:00" in panel._meta_label.text()


def test_show_record_displays_plate_badge_reasons_and_ocr_line(shown_panel, qapp) -> None:
    panel = shown_panel
    reasons = (UnverifiedReason.INSUFFICIENT_READINGS, UnverifiedReason.LOW_CONFIDENCE)
    panel.show_record(_record(ocr_text="ABD123", reasons=reasons), None, None)
    qapp.processEvents()
    assert panel._stack.currentWidget() is panel._body
    _assert_full_record(panel, reasons)

    panel.show_record(_record(), None, None)
    qapp.processEvents()
    assert (panel._ocr_label.isVisible(), panel._reasons_title.isVisible()) == (False, False)
    assert panel._reasons_label.text() == ""


def test_confirm_and_reject_emit_decisions(qapp) -> None:
    panel = ReviewPanel()
    decided: list[ReviewDecision] = []
    panel.decided.connect(decided.append)

    panel.confirm()
    assert decided == []

    panel.show_record(_record(), None, None)
    panel.confirm()
    panel.reject()
    assert [decision.action for decision in decided] == [
        ReviewAction.CONFIRM,
        ReviewAction.REJECT,
    ]


def test_edit_correct_emits_corrected_text(qapp) -> None:
    panel = ReviewPanel()
    decided: list[ReviewDecision] = []
    panel.decided.connect(decided.append)
    panel.show_record(_record(), None, None)

    panel.start_edit()
    assert panel.is_editing() is True
    QTest.keyClicks(panel._edit, "xyz98k")
    assert panel._edit.text() == "XYZ98K"
    QTest.keyClick(panel._edit, Qt.Key.Key_Return)

    assert decided == [ReviewDecision(ReviewAction.CORRECT, "XYZ98K")]
    assert panel.is_editing() is False


def test_edit_same_text_confirms(qapp) -> None:
    panel = ReviewPanel()
    decided: list[ReviewDecision] = []
    panel.decided.connect(decided.append)
    panel.show_record(_record(), None, None)

    panel.start_edit()
    QTest.keyClick(panel._edit, Qt.Key.Key_Return)

    assert decided == [ReviewDecision(ReviewAction.CONFIRM)]
    assert panel.is_editing() is False


def test_edit_invalid_text_shows_message(qapp) -> None:
    panel = ReviewPanel()
    decided: list[ReviewDecision] = []
    panel.decided.connect(decided.append)
    panel.show_record(_record(), None, None)

    panel.start_edit()
    panel._edit.clear()
    QTest.keyClick(panel._edit, Qt.Key.Key_Return)

    assert panel._error_label.text() == INVALID_MESSAGE
    assert panel.is_editing() is True
    assert decided == []

    QTest.keyClick(panel._edit, Qt.Key.Key_Escape)
    assert panel.is_editing() is False
    assert decided == []
    assert panel._error_label.text() == ""


def test_disabled_actions_do_not_emit_and_show_note(shown_panel, qapp) -> None:
    panel = shown_panel
    decided: list[ReviewDecision] = []
    skips: list[int] = []
    panel.decided.connect(decided.append)
    panel.skip_requested.connect(lambda: skips.append(1))
    panel.show_record(_record(), None, None)

    panel.set_actions_enabled(False)
    qapp.processEvents()
    assert panel._note_label.isVisible() is True
    assert panel._note_label.text() == BUSY_MESSAGE
    assert all(not button.isEnabled() for button in panel._buttons)
    for call in (panel.confirm, panel.reject, panel.skip, panel.start_edit):
        call()
    assert (decided, skips, panel.is_editing()) == ([], [], False)


def test_reenabling_actions_restores_buttons(shown_panel, qapp) -> None:
    panel = shown_panel
    decided: list[ReviewDecision] = []
    panel.decided.connect(decided.append)
    panel.show_record(_record(), None, None)

    panel.set_actions_enabled(False)
    panel.set_actions_enabled(True)
    qapp.processEvents()
    assert panel._note_label.isVisible() is False
    assert all(button.isEnabled() for button in panel._buttons)
    panel.confirm()
    assert [decision.action for decision in decided] == [ReviewAction.CONFIRM]
