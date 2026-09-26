from __future__ import annotations

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.cer import character_error_rate, exact_match_rate, levenshtein


@pytest.mark.parametrize(
    "a,b,d",
    [
        ("", "", 0),
        ("ABC123", "ABC123", 0),
        ("ABC123", "ABC128", 1),
        ("ABC12", "ABC123", 1),
        ("XBC123", "ABC12", 2),
        ("", "ABC", 3),
    ],
)
def test_levenshtein(a: str, b: str, d: int) -> None:
    assert levenshtein(a, b) == d


def test_rates() -> None:
    pairs = [("ABC123", "ABC123"), ("ABC128", "ABC123"), ("XYZ98", "XYZ98K")]
    assert character_error_rate(pairs) == pytest.approx(2 / 18)
    assert exact_match_rate(pairs) == pytest.approx(1 / 3)


def test_empty_raises() -> None:
    with pytest.raises(EvaluationError):
        character_error_rate([])
    with pytest.raises(EvaluationError):
        exact_match_rate([])
