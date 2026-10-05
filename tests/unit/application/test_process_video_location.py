from __future__ import annotations

from pathlib import Path

from lector_placas.domain.entities import PlateLocation
from tests.unit.application.test_process_video import SHA, build


def test_saved_sighting_has_plate_location() -> None:
    process, parts = build([i * 100 for i in range(10)])
    process.execute(Path("v.mp4"), SHA)
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert record.location == PlateLocation(0, 130, 185, 100, 30)


def test_location_matches_crop_quality() -> None:
    process, parts = build([i * 100 for i in range(10)])
    process.execute(Path("v.mp4"), SHA)
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert record.location is not None and record.quality is not None
    assert record.location.width == record.quality.plate_width_px
    assert record.location.height == record.quality.plate_height_px
