"""Filtro de legibilidad: regresión softmax sobre características del avistamiento."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lector_placas.domain.entities import (
    ConsolidatedPlate,
    CropQuality,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import InvalidEntityError

if TYPE_CHECKING:
    from collections.abc import Sequence

FEATURE_COUNT: Final[int] = 16
CLASS_COUNT: Final[int] = 3
REASON_FEATURES: Final[tuple[UnverifiedReason, ...]] = tuple(UnverifiedReason)[:8]


@dataclass(frozen=True, slots=True)
class LegibilityModel:
    """Coeficientes del modelo de legibilidad (3 clases: legible, borrosa, no placa)."""

    mean: tuple[float, ...]
    std: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    bias: tuple[float, ...]
    threshold: float

    def __post_init__(self) -> None:
        """Valida dimensiones, desviaciones y umbral.

        Raises:
            InvalidEntityError: si el modelo es inválido.
        """
        valid = (
            len(self.mean) == FEATURE_COUNT
            and len(self.std) == FEATURE_COUNT
            and len(self.weights) == CLASS_COUNT
            and all(len(row) == FEATURE_COUNT for row in self.weights)
            and len(self.bias) == CLASS_COUNT
            and all(value > 0 for value in self.std)
            and 0 <= self.threshold < 1
        )
        if not valid:
            raise InvalidEntityError("modelo de legibilidad inválido")


def feature_vector(
    plate: ConsolidatedPlate,
    quality: CropQuality,
    frame_width: int,
    frame_height: int,
    vehicle_type: VehicleType,
) -> tuple[float, ...]:
    """Construye el vector de 16 características de un avistamiento."""
    base = (
        plate.confidence,
        plate.agreement,
        math.log(plate.num_readings),
        quality.plate_width_px / max(frame_width, frame_height),
        quality.plate_height_px / quality.plate_width_px,
        math.log1p(quality.sharpness),
        quality.contrast / 128.0,
        1.0 if vehicle_type is VehicleType.MOTORCYCLE else 0.0,
    )
    flags = tuple(1.0 if reason in plate.reasons else 0.0 for reason in REASON_FEATURES)
    return base + flags


def predict(model: LegibilityModel, features: Sequence[float]) -> tuple[float, float, float]:
    """Devuelve `(p_legible, p_borrosa, p_no_placa)` mediante softmax."""
    z = [(features[j] - model.mean[j]) / model.std[j] for j in range(FEATURE_COUNT)]
    logits = [
        sum(model.weights[c][j] * z[j] for j in range(FEATURE_COUNT)) + model.bias[c]
        for c in range(CLASS_COUNT)
    ]
    top = max(logits)
    exps = [math.exp(value - top) for value in logits]
    total = sum(exps)
    return (exps[0] / total, exps[1] / total, exps[2] / total)


def legibility_reason(model: LegibilityModel, features: Sequence[float]) -> UnverifiedReason | None:
    """Devuelve la razón de rechazo si la probabilidad de legible queda bajo el umbral."""
    probs = predict(model, features)
    if probs[0] >= model.threshold:
        return None
    if probs[2] > probs[1]:
        return UnverifiedReason.PREDICTED_NOT_PLATE
    return UnverifiedReason.PREDICTED_ILLEGIBLE
