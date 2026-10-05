"""Tests de la consulta low_quality."""

from __future__ import annotations

import pytest

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
from lector_placas.domain.errors import InvalidEntityError
from tests.fixtures.fakes import InMemoryPlateRepository, fake_sighting_record


def test_default_includes_everything() -> None:
    """Sin parámetros, low_quality='include' devuelve todos los avistamientos."""
    a = fake_sighting_record(
        sighting_id=1,
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    d = fake_sighting_record(
        sighting_id=4,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_NOT_PLATE),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c, d]:
        browser.records[record.sighting_id] = record
    results = browser.search_sightings(SightingQuery(), 10, 0)
    assert len(results) == 4
    assert [r.sighting_id for r in results] == [4, 3, 2, 1]


def test_exclude_and_only() -> None:
    """low_quality='exclude' excluye predicted_*; 'only' solo devuelve predicted_*."""
    a = fake_sighting_record(
        sighting_id=1,
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    d = fake_sighting_record(
        sighting_id=4,
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_NOT_PLATE),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c, d]:
        browser.records[record.sighting_id] = record
    exclude_results = browser.search_sightings(SightingQuery(low_quality="exclude"), 10, 0)
    assert len(exclude_results) == 2
    assert [r.sighting_id for r in exclude_results] == [2, 1]
    assert browser.count_sightings(SightingQuery(low_quality="exclude")) == 2
    only_results = browser.search_sightings(SightingQuery(low_quality="only"), 10, 0)
    assert len(only_results) == 2
    assert [r.sighting_id for r in only_results] == [4, 3]
    assert browser.count_sightings(SightingQuery(low_quality="only")) == 2


def test_invalid_value() -> None:
    """low_quality con valor inválido lanza InvalidEntityError."""
    with pytest.raises(InvalidEntityError, match="low_quality inválido"):
        SightingQuery(low_quality="otro")  # type: ignore
