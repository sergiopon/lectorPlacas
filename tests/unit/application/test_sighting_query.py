from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import ReviewStatus
from lector_placas.domain.errors import InvalidEntityError

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def test_query_defaults_are_valid() -> None:
    query = SightingQuery()
    assert (query.status, query.plate_prefix, query.run_id) == (None, None, None)
    assert query.created_from is None
    assert query.created_to is None


def test_query_accepts_valid_filters() -> None:
    query = SightingQuery(
        status=ReviewStatus.CONFIRMED,
        plate_prefix="ABC123",
        run_id=1,
        created_from=NOW,
        created_to=NOW + timedelta(hours=1),
    )
    assert query.plate_prefix == "ABC123"
    assert query.run_id == 1


@pytest.mark.parametrize("prefix", ["ab1", "", "ABC-12", "ABCDEFGHIJK"])
def test_query_rejects_invalid_prefix(prefix: str) -> None:
    with pytest.raises(InvalidEntityError) as excinfo:
        SightingQuery(plate_prefix=prefix)
    assert str(excinfo.value) == "plate_prefix inválido"


def test_query_rejects_run_id_below_one() -> None:
    for run_id in (0, -1):
        with pytest.raises(InvalidEntityError):
            SightingQuery(run_id=run_id)


def test_query_rejects_naive_dates() -> None:
    naive = datetime(2026, 9, 24, 12, 0)
    with pytest.raises(InvalidEntityError):
        SightingQuery(created_from=naive)
    with pytest.raises(InvalidEntityError):
        SightingQuery(created_to=naive)


def test_query_rejects_inverted_range() -> None:
    with pytest.raises(InvalidEntityError):
        SightingQuery(created_from=NOW, created_to=NOW)
    with pytest.raises(InvalidEntityError):
        SightingQuery(created_from=NOW, created_to=NOW - timedelta(hours=1))
