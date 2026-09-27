"""Métricas de precisión, recall y F1 del detector de placas (spec 037)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import EvaluationError

IOU_THRESHOLD: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class DetectionCounts:
    """Conteo de aciertos, falsos positivos y falsos negativos de una imagen."""

    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    """Métricas agregadas del detector sobre un split completo."""

    images: int
    counts: DetectionCounts
    precision: float | None
    recall: float | None
    f1: float | None


def iou(a: BoundingBox, b: BoundingBox) -> float:
    """Calcula la intersección sobre unión de dos cajas.

    Args:
        a: primera caja.
        b: segunda caja.

    Returns:
        La IoU en [0, 1]; 0.0 si no se solapan o si la unión es 0.
    """
    intersection = _intersection_area(a, b)
    union = a.area + b.area - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def match_image(
    predictions: Sequence[PlateDetection],
    truths: Sequence[BoundingBox],
    threshold: float = IOU_THRESHOLD,
) -> DetectionCounts:
    """Empareja predicciones y verdades de una imagen por IoU.

    Las predicciones se ordenan por confianza descendente (orden estable) y cada una
    busca entre las verdades aún no emparejadas la de mayor IoU: si alcanza el umbral
    es un acierto y la verdad queda emparejada; si no, es un falso positivo.

    Args:
        predictions: detecciones del detector (cajas en píxeles).
        truths: cajas verdaderas en píxeles.
        threshold: IoU mínimo para considerar un emparejamiento.

    Returns:
        Los conteos de la imagen; las verdades sin emparejar son falsos negativos.
    """
    unmatched = list(range(len(truths)))
    true_positives = 0
    false_positives = 0
    for prediction in sorted(predictions, key=_confidence, reverse=True):
        index = _best_match(prediction.box, truths, unmatched, threshold)
        if index is None:
            false_positives += 1
        else:
            true_positives += 1
            unmatched.remove(index)
    return DetectionCounts(true_positives, false_positives, len(unmatched))


def summarize(per_image: Sequence[DetectionCounts]) -> DetectionMetrics:
    """Agrega los conteos por imagen y calcula precisión, recall y F1.

    Args:
        per_image: conteos de cada imagen evaluada; no puede estar vacío.

    Returns:
        Las métricas agregadas; una métrica sin denominador es `None`.

    Raises:
        EvaluationError: si no hay imágenes para evaluar.
    """
    if not per_image:
        raise EvaluationError("no hay imágenes para evaluar")
    counts = DetectionCounts(
        sum(item.true_positives for item in per_image),
        sum(item.false_positives for item in per_image),
        sum(item.false_negatives for item in per_image),
    )
    precision = _ratio(counts.true_positives, counts.true_positives + counts.false_positives)
    recall = _ratio(counts.true_positives, counts.true_positives + counts.false_negatives)
    return DetectionMetrics(len(per_image), counts, precision, recall, _f1(precision, recall))


def _intersection_area(a: BoundingBox, b: BoundingBox) -> float:
    """Área de la intersección de dos cajas; 0.0 si no se solapan."""
    width = min(a.x2, b.x2) - max(a.x1, b.x1)
    height = min(a.y2, b.y2) - max(a.y1, b.y1)
    if width <= 0.0 or height <= 0.0:
        return 0.0
    return width * height


def _confidence(prediction: PlateDetection) -> float:
    """Clave de ordenación: confianza de la detección."""
    return prediction.confidence


def _best_match(
    box: BoundingBox, truths: Sequence[BoundingBox], unmatched: list[int], threshold: float
) -> int | None:
    """Índice de la verdad no emparejada de mayor IoU, o `None` si ninguna alcanza el umbral."""
    best_index: int | None = None
    best_iou = 0.0
    for index in unmatched:
        value = iou(box, truths[index])
        if value > best_iou:
            best_iou = value
            best_index = index
    if best_index is None or best_iou < threshold:
        return None
    return best_index


def _ratio(numerator: int, denominator: int) -> float | None:
    """Cociente, o `None` si el denominador es 0."""
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    """Media armónica de precisión y recall, o `None` si no se puede calcular."""
    if precision is None or recall is None or precision + recall == 0.0:
        return None
    return 2 * precision * recall / (precision + recall)
