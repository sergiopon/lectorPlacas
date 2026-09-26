from __future__ import annotations

import pytest

from lector_placas.domain.privacy import mask_plate


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ABC123", "A****3"),
        ("XYZ98K", "X****K"),
        ("AB", "**"),
        ("A", "*"),
        ("", ""),
    ],
)
def test_mask_plate(text: str, expected: str) -> None:
    assert mask_plate(text) == expected
