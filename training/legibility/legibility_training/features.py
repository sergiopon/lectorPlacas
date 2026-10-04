from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np

from legibility_training.common import REASONS, LegibilityError

if TYPE_CHECKING:
    from legibility_training.dataset import Row


FEATURE_NAMES: Final[tuple[str, ...]] = (
    "confidence",
    "agreement",
    "log_num_readings",
    "relative_width",
    "aspect",
    "log_sharpness",
    "contrast",
    "is_motorcycle",
    *[f"reason_{r}" for r in REASONS],
)


def feature_vector(row: Row) -> np.ndarray:
    """Calcula el vector de características (float64, longitud 16)."""
    if (
        row.plate_width_px is None
        or row.plate_height_px is None
        or row.sharpness is None
        or row.contrast is None
        or row.frame_width is None
        or row.frame_height is None
    ):
        raise LegibilityError("fila sin medidas")

    features = [
        float(row.confidence),
        float(row.agreement),
        math.log(row.num_readings),
        row.plate_width_px / max(row.frame_width, row.frame_height),
        row.plate_height_px / row.plate_width_px,
        math.log1p(row.sharpness),
        row.contrast / 128.0,
        1.0 if row.vehicle_type == "motorcycle" else 0.0,
    ]

    for reason in REASONS:
        features.append(1.0 if reason in row.reasons else 0.0)

    return np.array(features, dtype=np.float64)
