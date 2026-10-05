"""Tests de aceptación: la placa leída debe estar dentro del vehículo seguido."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from lector_placas.domain.entities import BoundingBox, PlateDetection
from tests.unit.application.test_process_video_proximity import SHA, build


class TwoPlateDetector:
    """Devuelve una placa ajena (más confiable) y una propia (menos confiable)."""

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        return [
            PlateDetection(BoundingBox(300, 100, 400, 130), 0.95),
            PlateDetection(BoundingBox(50, 100, 150, 130), 0.80),
        ]


class OutsidePlateDetector:
    """Devuelve solo una placa cuyo centro cae fuera del vehículo."""

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        return [PlateDetection(BoundingBox(300, 100, 400, 130), 0.95)]


def test_prefers_plate_inside_vehicle() -> None:
    """Se elige la placa propia aunque la ajena tenga mayor confianza."""
    process, parts = build(plates=TwoPlateDetector())
    process.execute(Path("v.mp4"), SHA)
    sightings = parts["repo"].list_sightings(None, 10, 0)
    assert sightings
    location = sightings[0].location
    assert location is not None
    assert location.x == 130
    assert location.width == 100


def test_plate_outside_vehicle_is_discarded(caplog) -> None:  # type: ignore[no-untyped-def]
    """Una placa fuera del vehículo se descarta y se cuenta en el log."""
    caplog.set_level(logging.INFO)
    process, parts = build(plates=OutsidePlateDetector())
    result = process.execute(Path("v.mp4"), SHA)
    assert parts["repo"].list_sightings(None, 10, 0) == []
    assert result.stats.tracks_without_reading == 1
    expected = "sin_placa=0 placa_en_borde=0 placa_estrecha=0 borrosa=0 placa_fuera_vehiculo=3"
    assert any(expected in rec.message for rec in caplog.records)
