from __future__ import annotations

import pytest

from lector_placas.domain.errors import (
    InvalidEntityError,
    InvalidPlateTextError,
    PlateFormatCatalogError,
)
from lector_placas.domain.ocr_correction import ConfusionMap, correct_to_pattern

DEFAULT = ConfusionMap.default()


def test_default_pairs() -> None:
    assert DEFAULT.pairs == (("O", "0"), ("I", "1"), ("B", "8"), ("S", "5"))


def test_to_digit_and_to_letter() -> None:
    assert DEFAULT.to_digit("O") == "0"
    assert DEFAULT.to_digit("X") == "X"
    assert DEFAULT.to_letter("8") == "B"
    assert DEFAULT.to_letter("7") == "7"


@pytest.mark.parametrize(
    "text,pattern,expected",
    [
        ("ABC12S", "LLLDDD", "ABC125"),
        ("ABC12S", "LLLDDL", "ABC12S"),
        ("ABC125", "LLLDDL", "ABC12S"),
        ("A8C1O3", "LLLDDD", "ABC103"),
        ("0BC123", "LLLDDD", "OBC123"),
        ("ABC12X", "LLLDDD", "ABC12X"),
        ("OI8BOS", "DDDLLL", "018BOS"),
    ],
)
def test_correct_to_pattern(text: str, pattern: str, expected: str) -> None:
    assert correct_to_pattern(text, pattern, DEFAULT) == expected


def test_empty_map_changes_nothing() -> None:
    assert correct_to_pattern("A8C1O3", "LLLDDD", ConfusionMap(())) == "A8C1O3"


def test_length_mismatch_raises() -> None:
    with pytest.raises(InvalidPlateTextError):
        correct_to_pattern("ABC12", "LLLDDD", DEFAULT)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(InvalidPlateTextError):
        correct_to_pattern("abc123", "LLLDDD", DEFAULT)
    with pytest.raises(PlateFormatCatalogError):
        correct_to_pattern("ABC123", "LLLXXX", DEFAULT)


@pytest.mark.parametrize(
    "pairs",
    [
        (("O", "0"), ("O", "1")),
        (("O", "0"), ("Q", "0")),
        (("OO", "0"),),
        (("O", "A"),),
    ],
)
def test_confusion_map_rejects_invalid(pairs: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(InvalidEntityError):
        ConfusionMap(pairs)
