"""Métricas M-01..M-03: emparejamiento voraz contra el ground truth (docs/04-evaluacion.md §3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.evaluation.ground_truth import GroundTruth, GroundTruthPlate

TOLERANCE_MS: Final[int] = 1000
CONFIRMED_ONLY: Final[frozenset[ReviewStatus]] = frozenset({ReviewStatus.CONFIRMED})
ANY_STATUS: Final[frozenset[ReviewStatus]] = frozenset(
    {ReviewStatus.CONFIRMED, ReviewStatus.UNVERIFIED, ReviewStatus.CORRECTED}
)


@dataclass(frozen=True, slots=True)
class PlateMetrics:
    """Conteos y tasas de M-01..M-03 para una corrida."""

    gt_legible: int
    confirmed_total: int
    confirmed_matched: int
    any_matched: int
    corrected_total: int
    gt_far_excluded: int = 0
    confirmed_matched_near: int | None = None
    min_plate_width: int | None = None

    @property
    def precision_confirmed(self) -> float | None:
        """M-01: confirmadas emparejadas entre confirmadas totales; `None` sin denominador."""
        return _ratio(self.confirmed_matched, self.confirmed_total)

    @property
    def recall_any(self) -> float | None:
        """M-02: placas legibles emparejadas con cualquier estado; `None` sin denominador."""
        return _ratio(self.any_matched, self.gt_legible)

    @property
    def recall_confirmed(self) -> float | None:
        """M-03: placas legibles emparejadas con una confirmada; `None` sin denominador."""
        matched = (
            self.confirmed_matched
            if self.confirmed_matched_near is None
            else self.confirmed_matched_near
        )
        return _ratio(matched, self.gt_legible)


def overlaps(record: SightingRecord, plate: GroundTruthPlate, tolerance_ms: int) -> bool:
    """Indica si el intervalo del avistamiento solapa el de la placa con la tolerancia dada."""
    return (
        record.first_seen_ms <= plate.last_seen_ms + tolerance_ms
        and plate.first_seen_ms <= record.last_seen_ms + tolerance_ms
    )


def greedy_match(
    records: Sequence[SightingRecord],
    plates: Sequence[GroundTruthPlate],
    statuses: frozenset[ReviewStatus],
    tolerance_ms: int,
) -> int:
    """Empareja avistamientos con placas legibles, uno a uno y en orden temporal.

    Args:
        records: avistamientos de la corrida.
        plates: placas del ground truth.
        statuses: estados de avistamiento admitidos.
        tolerance_ms: tolerancia de solapamiento temporal, en milisegundos.

    Returns:
        El número de parejas formadas.
    """
    legibles = [plate for plate in plates if plate.legible]
    considered = sorted(
        (record for record in records if record.status in statuses),
        key=lambda record: (record.first_seen_ms, record.sighting_id),
    )
    used = [False] * len(legibles)
    matched = 0
    for record in considered:
        for index, plate in enumerate(legibles):
            if used[index] or record.plate_text != plate.text:
                continue
            if overlaps(record, plate, tolerance_ms):
                used[index] = True
                matched += 1
                break
    return matched


def compute_metrics(
    records: Sequence[SightingRecord],
    truth: GroundTruth,
    tolerance_ms: int = TOLERANCE_MS,
    min_plate_width: int | None = None,
) -> PlateMetrics:
    """Calcula los conteos y las tasas de M-01..M-03 de una corrida.

    Args:
        records: avistamientos de la corrida.
        truth: ground truth del video.
        tolerance_ms: tolerancia de solapamiento temporal, en milisegundos.
        min_plate_width: ancho mínimo de placa efectivo del perfil, en píxeles;
            `None` (o ground truth versión 1) considera cercanas todas las legibles.

    Returns:
        Los conteos y tasas de la corrida.
    """
    legibles = [plate for plate in truth.plates if plate.legible]
    cercanas = (
        legibles
        if min_plate_width is None or truth.version == 1
        else [plate for plate in legibles if _is_near(plate, min_plate_width)]
    )
    return PlateMetrics(
        gt_legible=len(cercanas),
        confirmed_total=sum(1 for record in records if record.status is ReviewStatus.CONFIRMED),
        confirmed_matched=greedy_match(records, legibles, CONFIRMED_ONLY, tolerance_ms),
        any_matched=greedy_match(records, cercanas, ANY_STATUS, tolerance_ms),
        corrected_total=sum(1 for record in records if record.status is ReviewStatus.CORRECTED),
        gt_far_excluded=len(legibles) - len(cercanas),
        confirmed_matched_near=greedy_match(records, cercanas, CONFIRMED_ONLY, tolerance_ms),
        min_plate_width=None if truth.version == 1 else min_plate_width,
    )


def _is_near(plate: GroundTruthPlate, min_plate_width: int) -> bool:
    """Indica si una placa legible es cercana según su ancho máximo."""
    return plate.max_plate_width_px is not None and plate.max_plate_width_px >= min_plate_width


def _ratio(numerator: int, denominator: int) -> float | None:
    """Devuelve el cociente o `None` si el denominador es cero."""
    if denominator == 0:
        return None
    return numerator / denominator
