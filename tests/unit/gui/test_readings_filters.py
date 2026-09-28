from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtTest import QTest

from lector_placas.application.ports import RunRecord, RunStatus
from lector_placas.domain.entities import ReviewStatus
from lector_placas.gui.labels import profile_label
from lector_placas.gui.readings_filters import FILTER_ORDER, ReadingsFilters

STARTED_AT = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)


def _run(run_id: int, profile: str = "calle_lenta") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        profile=profile,
        status=RunStatus.COMPLETED,
        started_at=STARTED_AT,
        finished_at=STARTED_AT,
        duration_ms=60_000,
        frames_processed=100,
        sightings_confirmed=1,
        sightings_unverified=0,
        tracks_without_reading=0,
        processing_ms=1000,
    )


def test_counts_render_in_buttons(qapp) -> None:
    filters = ReadingsFilters()
    filters.set_counts(
        {
            ReviewStatus.UNVERIFIED: 3,
            ReviewStatus.CONFIRMED: 1,
            ReviewStatus.CORRECTED: 0,
            ReviewStatus.REJECTED: 0,
            None: 5,
        }
    )
    assert filters._buttons[ReviewStatus.UNVERIFIED].text() == "Por revisar (3)"
    assert filters._buttons[ReviewStatus.CONFIRMED].text() == "Confirmadas (1)"
    assert filters._buttons[ReviewStatus.CORRECTED].text() == "Corregidas (0)"
    assert filters._buttons[ReviewStatus.REJECTED].text() == "Descartadas (0)"
    assert filters._buttons[None].text() == "Todas (5)"

    filters.set_counts({})
    assert filters._buttons[ReviewStatus.UNVERIFIED].text() == "Por revisar (0)"
    assert filters._buttons[None].text() == "Todas (0)"


def test_illegible_filter_button(qapp) -> None:
    filters = ReadingsFilters()
    assert filters._buttons[ReviewStatus.ILLEGIBLE].text() == "Borrosas (0)"

    filters.set_counts({ReviewStatus.ILLEGIBLE: 4})
    assert filters._buttons[ReviewStatus.ILLEGIBLE].text() == "Borrosas (4)"

    order = [filters._buttons[status] for status in FILTER_ORDER]
    index = order.index(filters._buttons[ReviewStatus.ILLEGIBLE])
    assert order[index - 1] is filters._buttons[ReviewStatus.REJECTED]
    assert order[index + 1] is filters._buttons[None]


def test_set_status_does_not_emit_but_click_does(qapp) -> None:
    filters = ReadingsFilters()
    received: list[int] = []
    filters.changed.connect(lambda: received.append(1))

    filters.set_status(ReviewStatus.CONFIRMED)
    assert received == []
    assert filters.status() is ReviewStatus.CONFIRMED
    assert filters._buttons[ReviewStatus.CONFIRMED].isChecked() is True
    assert filters._buttons[ReviewStatus.UNVERIFIED].isChecked() is False

    filters._buttons[ReviewStatus.REJECTED].click()
    assert len(received) == 1
    assert filters.status() is ReviewStatus.REJECTED


def test_search_is_debounced_and_uppercased(qapp) -> None:
    filters = ReadingsFilters()
    received: list[int] = []
    filters.changed.connect(lambda: received.append(1))

    QTest.keyClicks(filters._search, "xyz98k")
    assert received == []

    QTest.qWait(400)
    assert len(received) == 1
    assert filters.plate_prefix() == "XYZ98K"

    filters._search.clear()
    QTest.qWait(400)
    assert len(received) == 2
    assert filters.plate_prefix() is None


def test_runs_combo_lists_runs_and_keeps_selection(qapp) -> None:
    filters = ReadingsFilters()
    received: list[int] = []
    filters.changed.connect(lambda: received.append(1))
    run_one, run_two = _run(1, "parqueadero"), _run(2)

    filters.set_runs([run_two, run_one])
    started = STARTED_AT.astimezone().strftime("%d/%m %H:%M")
    assert (filters._runs.count(), filters._runs.itemText(0)) == (3, "Todos los videos")
    assert filters._runs.itemText(1) == f"Video 2 · {started} · {profile_label('calle_lenta')}"
    assert (filters.run_id(), received) == (None, [])

    filters.set_run_id(2)
    assert (filters.run_id(), received) == (2, [])

    filters.set_runs([run_two, run_one])
    assert filters.run_id() == 2

    filters.set_runs([run_one])
    assert filters.run_id() is None

    filters._runs.setCurrentIndex(1)
    assert (received, filters.run_id()) == ([1], 1)
