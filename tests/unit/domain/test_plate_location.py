from __future__ import annotations

import pytest

from lector_placas.domain.entities import PlateLocation
from lector_placas.domain.errors import InvalidEntityError
from tests.fixtures.fakes import fake_sighting_record


def test_valid_location() -> None:
    location = PlateLocation(1500, 10, 20, 60, 30)
    assert location.frame_ms == 1500
    assert location.x == 10
    assert location.y == 20
    assert location.width == 60
    assert location.height == 30


@pytest.mark.parametrize(
    "args",
    [(-1, 0, 0, 1, 1), (0, -1, 0, 1, 1), (0, 0, -1, 1, 1), (0, 0, 0, 0, 1), (0, 0, 0, 1, 0)],
)
def test_invalid_location(args: tuple[int, int, int, int, int]) -> None:
    with pytest.raises(InvalidEntityError):
        PlateLocation(*args)
    assert PlateLocation(0, 0, 0, 1, 1).width == 1


def test_records_default_to_no_location() -> None:
    assert fake_sighting_record().location is None
