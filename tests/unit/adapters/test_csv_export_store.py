from __future__ import annotations

import csv
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.adapters.export.csv_export_store import (
    HEADER,
    CsvExportStore,
    record_to_row,
    sanitize_cell,
)
from lector_placas.domain.entities import (
    ReviewStatus,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ExportError

T0 = datetime(2026, 9, 24, 12, 30, 5, tzinfo=UTC)
RECORD = SightingRecord(
    7,
    1,
    3,
    100,
    900,
    VehicleType.MOTORCYCLE,
    "XYZ98K",
    "XYZ98K",
    0.912345,
    0.5,
    4,
    ReviewStatus.UNVERIFIED,
    (UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_AGREEMENT),
    ("co_moto",),
    None,
    T0,
    None,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("=SUM(A1)", "'=SUM(A1)"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@x", "'@x"),
        ("ABC123", "ABC123"),
    ],
)
def test_sanitize_cell(value: str, expected: str) -> None:
    assert sanitize_cell(value) == expected


def test_record_to_row() -> None:
    row = record_to_row(RECORD)
    assert len(row) == len(HEADER)
    assert row[6] == "XYZ98K" and row[8] == "0.9123"
    assert row[12] == "low_confidence|low_agreement"
    assert row[14] == "2026-09-24T12:30:05.000000+00:00" and row[15] == ""


def test_write_creates_private_csv(tmp_path: Path) -> None:
    store = CsvExportStore(tmp_path / "exports")
    path = store.write_sightings([RECORD], T0)
    assert path.name == "sightings-20260924T123005Z.csv"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert tuple(rows[0]) == HEADER and rows[1][0] == "7"
    with pytest.raises(ExportError):
        store.write_sightings([RECORD], T0)


def test_delete_older_than(tmp_path: Path) -> None:
    store = CsvExportStore(tmp_path / "exports")
    assert store.delete_older_than(T0) == 0
    old = store.write_sightings([], T0)
    store.write_sightings([], T0 + timedelta(seconds=1))
    past = (datetime.now(UTC) - timedelta(days=100)).timestamp()
    os.utime(old, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=90)) == 1
    assert not old.exists()
