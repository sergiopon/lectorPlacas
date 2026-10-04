from __future__ import annotations

from pathlib import Path
from typing import Final

TRAINING_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = TRAINING_DIR / "datasets"
RUNS_DIR = TRAINING_DIR / "runs"


class LegibilityError(Exception):
    """Error en el entrenamiento de legibilidad."""

    pass


CLASSES: Final[tuple[str, str, str]] = ("legible", "borrosa", "no_placa")
REASONS: Final[tuple[str, ...]] = (
    "insufficient_readings",
    "low_confidence",
    "low_agreement",
    "unrecognized_format",
    "unverified_format",
    "vehicle_format_mismatch",
    "ambiguous_format",
    "correction_conflict",
)
MIN_PLATE_WIDTH_PX: Final[int] = 32
NEAR_MIN_WIDTH_FRAC: Final[float] = 0.025
MIN_PER_CLASS: Final[int] = 100
MIN_VIDEO_GROUPS: Final[int] = 4
MAX_HIDDEN_LEGIBLE: Final[float] = 0.05
BOOTSTRAP_ROUNDS: Final[int] = 2000
