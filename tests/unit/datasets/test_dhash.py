from __future__ import annotations

from lector_placas.datasets.dhash import dhash, hamming
from tests.unit.datasets.synthetic import noise


def test_dhash_identity_and_difference() -> None:
    assert hamming(dhash(noise(1)), dhash(noise(1))) == 0
    assert hamming(dhash(noise(1)), dhash(noise(2))) > 4
    assert 0 <= dhash(noise(3)) < 2**64
    assert hamming(0b1011, 0b0001) == 2
