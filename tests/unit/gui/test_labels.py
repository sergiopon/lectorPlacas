from __future__ import annotations

from datetime import UTC, datetime

from lector_placas.application.ports import RunStatus
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason, VehicleType
from lector_placas.gui.labels import (
    REASON_TEXTS,
    RUN_STATUS_LABELS,
    STATUS_BADGES,
    STATUS_LABELS,
    VEHICLE_LABELS,
    format_plate,
    local_datetime,
    percent,
    short_time,
    video_time,
)


def test_video_time_formats_examples() -> None:
    assert video_time(0) == "00:00.000"
    assert video_time(83_456) == "01:23.456"
    assert video_time(3_723_004) == "1:02:03.004"


def test_percent_rounds_fraction() -> None:
    assert percent(0.873) == "87 %"


def test_status_labels_cover_all_review_statuses() -> None:
    for status in ReviewStatus:
        assert status in STATUS_LABELS
        assert isinstance(STATUS_LABELS[status], str)
        assert STATUS_LABELS[status]


def test_vehicle_labels_cover_all_vehicle_types() -> None:
    for vehicle_type in VehicleType:
        assert vehicle_type in VEHICLE_LABELS
        assert isinstance(VEHICLE_LABELS[vehicle_type], str)
        assert VEHICLE_LABELS[vehicle_type]


def test_run_status_labels_cover_all_run_statuses() -> None:
    for status in RunStatus:
        assert status in RUN_STATUS_LABELS
        assert isinstance(RUN_STATUS_LABELS[status], str)
        assert RUN_STATUS_LABELS[status]


def test_local_datetime_uses_astimezone() -> None:
    value = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    text = local_datetime(value)
    assert text == value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def test_status_badges_and_reason_texts_cover_all_values() -> None:
    for status in ReviewStatus:
        assert isinstance(STATUS_BADGES[status], str)
        assert STATUS_BADGES[status]
    for reason in UnverifiedReason:
        assert isinstance(REASON_TEXTS[reason], str)
        assert REASON_TEXTS[reason]


def test_format_plate() -> None:
    assert format_plate("ABC123") == "ABC 123"
    assert format_plate("ABC12D") == "ABC 12D"
    assert format_plate("AB123") == "AB123"
    assert format_plate("ABCD1234") == "ABCD1234"


def test_short_time() -> None:
    assert short_time(0) == "0:00"
    assert short_time(83_456) == "1:23"
    assert short_time(3_723_004) == "1:02:03"
