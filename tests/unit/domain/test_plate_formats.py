from __future__ import annotations

import pytest

from lector_placas.domain.entities import PlateFormat, VehicleType
from lector_placas.domain.errors import InvalidPlateTextError, PlateFormatCatalogError
from lector_placas.domain.plate_formats import PlateFormatCatalog, text_pattern
from tests.fixtures.plate_catalog import build_test_catalog


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ABC123", "LLLDDD"),
        ("XYZ98K", "LLLDDL"),
        ("123ABC", "DDDLLL"),
        ("R12345", "LDDDDD"),
    ],
)
def test_text_pattern(text: str, expected: str) -> None:
    assert text_pattern(text) == expected


@pytest.mark.parametrize("text", ["", "abc123", "AB-123", "ABCDEFGHIJK"])
def test_text_pattern_rejects_invalid(text: str) -> None:
    with pytest.raises(InvalidPlateTextError):
        text_pattern(text)


def test_catalog_rejects_empty_and_duplicates() -> None:
    with pytest.raises(PlateFormatCatalogError):
        PlateFormatCatalog([])
    fmt = build_test_catalog().formats[0]
    with pytest.raises(PlateFormatCatalogError):
        PlateFormatCatalog([fmt, fmt])


def test_patterns_of_length_sorted_and_distinct() -> None:
    catalog = build_test_catalog()
    assert catalog.patterns_of_length(6) == ("DDDLLL", "LDDDDD", "LLDDDD", "LLLDDD", "LLLDDL")
    assert catalog.patterns_of_length(5) == ("LDDDD", "LLLDD")
    assert catalog.patterns_of_length(4) == ()


def test_matching_returns_catalog_order() -> None:
    ids = [f.format_id for f in build_test_catalog().matching("ABC123")]
    assert ids == ["co_particular_publico", "co_diplomatico_2015"]


def test_matching_moto_and_unverified() -> None:
    catalog = build_test_catalog()
    assert [f.format_id for f in catalog.matching("XYZ98K")] == ["co_moto"]
    assert [f.format_id for f in catalog.matching("R12345")] == ["co_remolque"]
    assert catalog.matching("") == ()


def test_matching_with_pattern_filters_pattern() -> None:
    catalog = build_test_catalog()
    assert catalog.matching_with_pattern("MCD123", "LLLDDD")[-1].format_id == "co_moto_diplomatica"
    assert catalog.matching_with_pattern("ABC123", "LLLDDL") == ()


def test_formats_property_keeps_input() -> None:
    fmt = PlateFormat("x_1", "c", "LD", "^[A-Z][0-9]$", True, frozenset({VehicleType.CAR}), "s")
    assert PlateFormatCatalog([fmt]).formats == (fmt,)
