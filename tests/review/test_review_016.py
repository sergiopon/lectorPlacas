"""Tests de aceptación adicionales.

Cubren un caso borde que la spec no enumera explícitamente: una detección con confianza
por debajo de `track_activation_threshold` no debe activar un track nuevo, aunque
`instant_first_frame_activation` esté activo.
"""

from __future__ import annotations

import numpy as np

from lector_placas.adapters.tracking.botsort_tracker import BotSortTracker, TrackerSettings
from lector_placas.domain.entities import BoundingBox, VehicleDetection, VehicleType

SETTINGS = TrackerSettings(30, 10.0, 0.7, 2, 0.2, 0.5, 0.3, 0.6, "sparseOptFlow", 2)
BACKGROUND = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)


def test_low_confidence_detection_does_not_create_track() -> None:
    """Una detección por debajo del umbral de activación no genera ningún track."""
    tracker = BotSortTracker(SETTINGS)
    low = VehicleDetection(BoundingBox(10, 10, 70, 50), 0.3, VehicleType.CAR)
    assert tracker.update([low], BACKGROUND, 0) == []
