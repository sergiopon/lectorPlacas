"""Tests de aceptación para la calidad de recorte en ProcessVideo."""

from __future__ import annotations

from pathlib import Path

from tests.unit.application.test_process_video import SHA, build


def test_saved_sighting_has_crop_quality() -> None:
    """El avistamiento guardado tiene la calidad del mejor recorte."""
    process, parts = build([i * 100 for i in range(10)])
    result = process.execute(Path("v.mp4"), SHA)
    assert result.run_id == 1
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert record.quality is not None
    assert record.quality.plate_width_px == 100
    assert record.quality.plate_height_px == 30
    assert record.quality.sharpness == 50.0
    assert record.quality.contrast == 0.0
