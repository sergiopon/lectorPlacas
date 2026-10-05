"""Filtros de proximidad para descartar vehículos y placas lejanas."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from lector_placas.domain.entities import BoundingBox

FRAME_EDGE_MARGIN_PX: Final[int] = 2
FULL_FRAME_ROI: Final[tuple[float, float, float, float]] = (0.0, 0.0, 1.0, 1.0)
NEAR_MIN_WIDTH_FRAC_MAX: Final[float] = 0.2


def effective_min_width(
    frame_width: int, frame_height: int, min_plate_width_px: int, near_min_width_frac: float
) -> int:
    """Calcula el ancho mínimo efectivo de una placa.

    Args:
        frame_width: ancho del frame en píxeles.
        frame_height: alto del frame en píxeles.
        min_plate_width_px: ancho mínimo de placa en píxeles.
        near_min_width_frac: fracción del mayor lado del frame que define el mínimo.

    Returns:
        El ancho mínimo efectivo, resultado de `math.ceil(round(max(...), 6))`.
    """
    return math.ceil(
        round(
            max(float(min_plate_width_px), near_min_width_frac * max(frame_width, frame_height)), 6
        )
    )


def center_in_roi(
    box: BoundingBox, roi: tuple[float, float, float, float], frame_width: int, frame_height: int
) -> bool:
    """Comprueba si el centro de una caja está dentro de la región de interés.

    Args:
        box: caja del vehículo o placa.
        roi: región de interés como (x1_frac, y1_frac, x2_frac, y2_frac) en [0, 1].
        frame_width: ancho del frame en píxeles.
        frame_height: alto del frame en píxeles.

    Returns:
        `True` si el centro está dentro de la ROI (bordes incluidos), `False` en caso contrario.
    """
    cx = (box.x1 + box.x2) / 2
    cy = (box.y1 + box.y2) / 2
    return (
        roi[0] * frame_width <= cx <= roi[2] * frame_width
        and roi[1] * frame_height <= cy <= roi[3] * frame_height
    )


def touches_frame_edge(box: BoundingBox, frame_width: int, frame_height: int) -> bool:
    """Comprueba si una caja toca o cruza el borde del frame.

    Args:
        box: caja a verificar.
        frame_width: ancho del frame en píxeles.
        frame_height: alto del frame en píxeles.

    Returns:
        `True` si la caja toca el borde (dentro del margen), `False` en caso contrario.
    """
    return (
        box.x1 < FRAME_EDGE_MARGIN_PX
        or box.y1 < FRAME_EDGE_MARGIN_PX
        or box.x2 > frame_width - FRAME_EDGE_MARGIN_PX
        or box.y2 > frame_height - FRAME_EDGE_MARGIN_PX
    )


def center_in_box(inner: BoundingBox, outer: BoundingBox) -> bool:
    """Comprueba si el centro de una caja está dentro de otra.

    Args:
        inner: caja cuyo centro se evalúa (su tamaño no importa).
        outer: caja contenedora.

    Returns:
        `True` si el centro de `inner` está dentro de `outer` (bordes incluidos).
    """
    cx = (inner.x1 + inner.x2) / 2
    cy = (inner.y1 + inner.y2) / 2
    return outer.x1 <= cx <= outer.x2 and outer.y1 <= cy <= outer.y2


def validate_roi(roi: tuple[float, float, float, float]) -> None:
    """Valida que una región de interés sea válida.

    Args:
        roi: región de interés como (x1, y1, x2, y2) en [0, 1].

    Raises:
        ValueError: si la ROI no cumple `0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1`.
    """
    if not (0.0 <= roi[0] < roi[2] <= 1.0 and 0.0 <= roi[1] < roi[3] <= 1.0):
        raise ValueError("roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1")


@dataclass(slots=True)
class ProximityCounters:
    """Contadores de descartes por filtros de proximidad en una corrida."""

    outside_roi: int = 0
    small_vehicle: int = 0
    no_plate: int = 0
    plate_at_edge: int = 0
    narrow_plate: int = 0
    blurry: int = 0
    plate_outside_vehicle: int = 0
