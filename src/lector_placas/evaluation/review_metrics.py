"""Métricas de calidad derivadas de las decisiones de revisión humana."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lector_placas.domain.entities import ReviewStatus, SightingRecord, UnverifiedReason
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.cer import character_error_rate, exact_match_rate

EMPTY_MESSAGE: Final[str] = "no hay avistamientos para evaluar"
VERDICT_STATUSES: Final[frozenset[ReviewStatus]] = frozenset(
    {ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED}
)
PREDICTED_REASONS: Final[frozenset[UnverifiedReason]] = frozenset(
    {UnverifiedReason.PREDICTED_ILLEGIBLE, UnverifiedReason.PREDICTED_NOT_PLATE}
)


@dataclass(frozen=True, slots=True)
class ReviewMetrics:
    """Resumen de precisión y CER calculado a partir de las decisiones guardadas."""

    confirmed_total: int
    confirmed_audited: int
    confirmed_kept: int
    confirmed_corrected: int
    confirmed_rejected: int
    precision_confirmed: float | None
    unverified_total: int
    unverified_confirmed: int
    unverified_corrected: int
    unverified_rejected: int
    unverified_pending: int
    reason_counts: dict[str, int]
    reviewed_readings: int
    cer: float | None
    exact_match_rate: float | None
    confirmed_illegible: int
    unverified_illegible: int
    hidden_total: int = 0
    hidden_legible: int = 0
    hidden_unusable: int = 0
    hidden_pending: int = 0


def compute_review_metrics(records: Sequence[SightingRecord]) -> ReviewMetrics:
    """Agrega las métricas de la revisión sobre los avistamientos indicados.

    Args:
        records: avistamientos a considerar, de cualquier estado.

    Returns:
        Las métricas agregadas; las tasas son `None` cuando no hay datos que las definan.

    Raises:
        EvaluationError: si `records` está vacío.
    """
    if not records:
        raise EvaluationError(EMPTY_MESSAGE)
    confirmed = [record for record in records if not record.reasons]
    unverified = [record for record in records if record.reasons]
    audited = [record for record in confirmed if record.reviewed_at is not None]
    pairs = _verdict_pairs(records)
    kept = _count(audited, ReviewStatus.CONFIRMED)
    hidden = [
        record
        for record in records
        if any(reason in PREDICTED_REASONS for reason in record.reasons)
    ]
    return ReviewMetrics(
        confirmed_total=len(confirmed),
        confirmed_audited=len(audited),
        confirmed_kept=kept,
        confirmed_corrected=_count(audited, ReviewStatus.CORRECTED),
        confirmed_rejected=_count(audited, ReviewStatus.REJECTED),
        precision_confirmed=_ratio(kept, len(audited)),
        unverified_total=len(unverified),
        unverified_confirmed=_count(unverified, ReviewStatus.CONFIRMED),
        unverified_corrected=_count(unverified, ReviewStatus.CORRECTED),
        unverified_rejected=_count(unverified, ReviewStatus.REJECTED),
        unverified_pending=_count(unverified, ReviewStatus.UNVERIFIED),
        reason_counts=_reason_counts(unverified),
        reviewed_readings=len(pairs),
        cer=character_error_rate(pairs) if pairs else None,
        exact_match_rate=exact_match_rate(pairs) if pairs else None,
        confirmed_illegible=_count(audited, ReviewStatus.ILLEGIBLE),
        unverified_illegible=_count(unverified, ReviewStatus.ILLEGIBLE),
        hidden_total=len(hidden),
        hidden_legible=sum(
            1
            for record in hidden
            if record.reviewed_at is not None
            and record.status in (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED)
        ),
        hidden_unusable=_count(hidden, ReviewStatus.REJECTED)
        + _count(hidden, ReviewStatus.ILLEGIBLE),
        hidden_pending=_count(hidden, ReviewStatus.UNVERIFIED),
    )


def _count(records: Sequence[SightingRecord], status: ReviewStatus) -> int:
    """Cuenta los avistamientos que quedaron con el estado indicado."""
    return sum(1 for record in records if record.status is status)


def _ratio(numerator: int, denominator: int) -> float | None:
    """Calcula el cociente, o `None` si no hay denominador."""
    return None if denominator == 0 else numerator / denominator


def _reason_counts(records: Sequence[SightingRecord]) -> dict[str, int]:
    """Cuenta cada razón una vez por avistamiento, con las claves en orden alfabético."""
    counter: Counter[str] = Counter()
    for record in records:
        counter.update({reason.value for reason in record.reasons})
    return dict(sorted(counter.items()))


def _verdict_pairs(records: Sequence[SightingRecord]) -> list[tuple[str, str]]:
    """Pares (texto del sistema, texto vigente) de los revisados con verdad conocida."""
    return [
        (record.ocr_text, record.plate_text)
        for record in records
        if record.reviewed_at is not None and record.status in VERDICT_STATUSES
    ]
