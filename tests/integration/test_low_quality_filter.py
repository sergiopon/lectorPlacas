"""Integración con SQLCipher para filtro low_quality (spec 064)."""

from __future__ import annotations

import pytest

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
from tests.fixtures.fakes import InMemoryPlateRepository, fake_sighting_record

pytestmark = pytest.mark.integration


def test_default_includes_everything() -> None:
    """Sin parámetros, low_quality='include' devuelve todos los avistamientos (SQLCipher)."""
    a = fake_sighting_record(
        sighting_id=1,
        plate_text="ABC123",
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        plate_text="DEF456",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        plate_text="GHI789",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    d = fake_sighting_record(
        sighting_id=4,
        plate_text="JKL012",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_NOT_PLATE),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c, d]:
        browser.records[record.sighting_id] = record
    results = browser.search_sightings(SightingQuery(), 10, 0)
    assert len(results) == 4
    assert [r.sighting_id for r in results] == [4, 3, 2, 1]


def test_low_quality_filter_with_exclude() -> None:
    """Filtra exclude: sin predicted_*."""
    a = fake_sighting_record(
        sighting_id=1,
        plate_text="ABC123",
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        plate_text="DEF456",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        plate_text="GHI789",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    d = fake_sighting_record(
        sighting_id=4,
        plate_text="JKL012",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_NOT_PLATE),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c, d]:
        browser.records[record.sighting_id] = record
    exclude_results = browser.search_sightings(SightingQuery(low_quality="exclude"), 10, 0)
    assert len(exclude_results) == 2
    assert [r.plate_text for r in exclude_results] == ["DEF456", "ABC123"]


def test_low_quality_filter_with_exclude_and_status() -> None:
    """Filtra exclude + status=UNVERIFIED: solo b."""
    a = fake_sighting_record(
        sighting_id=1,
        plate_text="ABC123",
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        plate_text="DEF456",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        plate_text="GHI789",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c]:
        browser.records[record.sighting_id] = record
    exclude_unverified = browser.search_sightings(
        SightingQuery(status=ReviewStatus.UNVERIFIED, low_quality="exclude"), 10, 0
    )
    assert len(exclude_unverified) == 1
    assert exclude_unverified[0].plate_text == "DEF456"


def test_low_quality_filter_with_only() -> None:
    """Filtra only: solo predicted_*."""
    a = fake_sighting_record(
        sighting_id=1,
        plate_text="ABC123",
        status=ReviewStatus.CONFIRMED,
        reasons=(),
    )
    b = fake_sighting_record(
        sighting_id=2,
        plate_text="DEF456",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE,),
    )
    c = fake_sighting_record(
        sighting_id=3,
        plate_text="GHI789",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,),
    )
    d = fake_sighting_record(
        sighting_id=4,
        plate_text="JKL012",
        status=ReviewStatus.UNVERIFIED,
        reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_NOT_PLATE),
    )
    browser = InMemoryPlateRepository()
    for record in [a, b, c, d]:
        browser.records[record.sighting_id] = record
    only_results = browser.search_sightings(SightingQuery(low_quality="only"), 10, 0)
    assert len(only_results) == 2
    assert [r.plate_text for r in only_results] == ["JKL012", "GHI789"]
