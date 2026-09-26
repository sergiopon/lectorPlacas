"""Consolidación por votación ponderada de las lecturas de un track (ADR-007)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from lector_placas.domain.entities import (
    ConsolidatedPlate,
    PlateFormat,
    PlateReading,
    ReviewStatus,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ConsolidationError, InvalidEntityError
from lector_placas.domain.ocr_correction import ConfusionMap, correct_to_pattern
from lector_placas.domain.plate_formats import PlateFormatCatalog

REL_TOL: float = 1e-9


@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    """Umbrales que deciden si un consolidado se confirma."""

    min_readings: int
    confirm_threshold: float
    min_agreement: float
    ambiguity_margin: float

    def __post_init__(self) -> None:
        """Valida el mínimo de lecturas y los tres umbrales unitarios.

        Raises:
            InvalidEntityError: Si `min_readings < 1` o algún umbral sale de [0, 1].
        """
        if self.min_readings < 1:
            raise InvalidEntityError(f"min_readings debe ser >= 1: {self.min_readings}")
        for name, value in (
            ("confirm_threshold", self.confirm_threshold),
            ("min_agreement", self.min_agreement),
            ("ambiguity_margin", self.ambiguity_margin),
        ):
            _require_unit_interval(value, name)


@dataclass(frozen=True, slots=True)
class _PatternOutcome:
    """Resultado de corregir y votar el grupo de lecturas con un patrón candidato."""

    text: str
    confidence: float
    agreement: float
    formats: tuple[PlateFormat, ...]


@dataclass(frozen=True, slots=True)
class _Selection:
    """Texto elegido por la selección de patrones y sus razones propias."""

    text: str
    confidence: float
    agreement: float
    format_ids: tuple[str, ...]
    reasons: tuple[UnverifiedReason, ...]


class VotingPlateConsolidator:
    """Consolida las lecturas de un track votando por carácter y por patrón."""

    def __init__(
        self,
        catalog: PlateFormatCatalog,
        policy: ConsolidationPolicy,
        confusions: ConfusionMap,
    ) -> None:
        """Guarda el catálogo de formatos, los umbrales y el mapa de confusiones."""
        self._catalog = catalog
        self._policy = policy
        self._confusions = confusions

    def consolidate(
        self, readings: Sequence[PlateReading], vehicle_type: VehicleType
    ) -> ConsolidatedPlate:
        """Convierte las lecturas de un track en una placa consolidada.

        Args:
            readings: Lecturas del mismo track; no puede estar vacía.
            vehicle_type: Tipo de vehículo del track, usado para desempatar formatos.

        Returns:
            Placa consolidada; confirmada solo si no acumula ninguna razón.

        Raises:
            ConsolidationError: Si no hay lecturas o provienen de tracks distintos.
        """
        _require_single_track(readings)
        length, length_tie = _target_length(readings)
        texts, confidences = _group_of_length(readings, length)
        selection = self._select(texts, confidences, length, vehicle_type)
        reasons = _collect_reasons(selection, length_tie, len(texts), self._policy)
        status = ReviewStatus.CONFIRMED if not reasons else ReviewStatus.UNVERIFIED
        return ConsolidatedPlate(
            selection.text,
            selection.confidence,
            selection.agreement,
            len(texts),
            status,
            reasons,
            selection.format_ids,
        )

    def _select(
        self,
        texts: list[str],
        confidences: list[tuple[float, ...]],
        length: int,
        vehicle_type: VehicleType,
    ) -> _Selection:
        """Elige el patrón ganador o, si no hay ninguno válido, el voto sin corregir."""
        outcomes = self._evaluate_patterns(texts, confidences, length)
        if not outcomes:
            text, confidence, agreement = _vote(texts, confidences, length)
            return _Selection(
                text,
                confidence,
                agreement,
                (),
                (UnverifiedReason.UNRECOGNIZED_FORMAT,),
            )
        compatible = [outcome for outcome in outcomes if _is_compatible(outcome, vehicle_type)]
        if not compatible:
            best = max(outcomes, key=lambda outcome: outcome.confidence)
            format_ids = tuple(fmt.format_id for fmt in best.formats)
            return _Selection(
                best.text,
                best.confidence,
                best.agreement,
                format_ids,
                (UnverifiedReason.VEHICLE_FORMAT_MISMATCH,),
            )
        ranked = sorted(compatible, key=lambda outcome: outcome.confidence, reverse=True)
        chosen = ranked[0]
        format_ids = tuple(
            fmt.format_id for fmt in chosen.formats if vehicle_type in fmt.vehicle_types
        )
        return _Selection(
            chosen.text,
            chosen.confidence,
            chosen.agreement,
            format_ids,
            _compatibility_reasons(ranked, vehicle_type, self._policy.ambiguity_margin),
        )

    def _evaluate_patterns(
        self, texts: list[str], confidences: list[tuple[float, ...]], length: int
    ) -> list[_PatternOutcome]:
        """Corrige y vota el grupo con cada patrón candidato que dé un formato válido."""
        outcomes: list[_PatternOutcome] = []
        for pattern in self._catalog.patterns_of_length(length):
            corrected = [correct_to_pattern(text, pattern, self._confusions) for text in texts]
            text, confidence, agreement = _vote(corrected, confidences, length)
            formats = self._catalog.matching_with_pattern(text, pattern)
            if formats:
                outcomes.append(_PatternOutcome(text, confidence, agreement, formats))
        return outcomes


def _require_single_track(readings: Sequence[PlateReading]) -> None:
    """Exige lecturas no vacías y todas del mismo track.

    Raises:
        ConsolidationError: Si `readings` está vacía o mezcla tracks distintos.
    """
    if not readings:
        raise ConsolidationError("no hay lecturas para consolidar")
    if len({reading.track_id for reading in readings}) > 1:
        raise ConsolidationError("lecturas de tracks distintos")


def _target_length(readings: Sequence[PlateReading]) -> tuple[int, bool]:
    """Longitud con mayor masa de confianza; empate → la mayor, marcado como empate."""
    mass: dict[int, float] = {}
    for reading in readings:
        mass[len(reading.text)] = mass.get(len(reading.text), 0.0) + reading.mean_confidence
    best = max(mass.values())
    tied = [length for length, value in mass.items() if math.isclose(value, best, rel_tol=REL_TOL)]
    return max(tied), len(tied) > 1


def _group_of_length(
    readings: Sequence[PlateReading], length: int
) -> tuple[list[str], list[tuple[float, ...]]]:
    """Textos y confianzas de las lecturas con esa longitud, en el orden recibido."""
    selected = [reading for reading in readings if len(reading.text) == length]
    return (
        [reading.text for reading in selected],
        [reading.char_confidences for reading in selected],
    )


def _vote(
    textos: list[str], confianzas: list[tuple[float, ...]], length: int
) -> tuple[str, float, float]:
    """Vota por posición ponderando con la confianza de cada carácter."""
    n = len(textos)
    winners = [_vote_position(textos, confianzas, position, n) for position in range(length)]
    text = "".join(character for character, _ in winners)
    confidence = min(score for _, score in winners)
    agreement = sum(1 for value in textos if value == text) / n
    return text, confidence, agreement


def _vote_position(
    textos: list[str], confianzas: list[tuple[float, ...]], position: int, n: int
) -> tuple[str, float]:
    """Carácter ganador de una posición y su score (`suma del ganador / n`)."""
    totals: dict[str, float] = {}
    for text, confidences in zip(textos, confianzas, strict=True):
        character = text[position]
        totals[character] = totals.get(character, 0.0) + confidences[position]
    winner = min(totals, key=lambda character: (-totals[character], character))
    return winner, totals[winner] / n


def _is_compatible(outcome: _PatternOutcome, vehicle_type: VehicleType) -> bool:
    """Indica si algún formato del resultado admite ese tipo de vehículo."""
    return any(vehicle_type in fmt.vehicle_types for fmt in outcome.formats)


def _compatibility_reasons(
    ranked: list[_PatternOutcome], vehicle_type: VehicleType, margin: float
) -> tuple[UnverifiedReason, ...]:
    """Razones del ganador: formato ambiguo y formato compatible sin verificar."""
    reasons: list[UnverifiedReason] = []
    if len(ranked) > 1 and ranked[0].confidence - ranked[1].confidence < margin:
        reasons.append(UnverifiedReason.AMBIGUOUS_FORMAT)
    if not _has_verified_format(ranked[0], vehicle_type):
        reasons.append(UnverifiedReason.UNVERIFIED_FORMAT)
    return tuple(reasons)


def _has_verified_format(outcome: _PatternOutcome, vehicle_type: VehicleType) -> bool:
    """Indica si algún formato compatible del resultado está verificado."""
    return any(fmt.verified and vehicle_type in fmt.vehicle_types for fmt in outcome.formats)


def _collect_reasons(
    selection: _Selection, length_tie: bool, n: int, policy: ConsolidationPolicy
) -> tuple[UnverifiedReason, ...]:
    """Une las razones con las métricas, sin duplicados y en el orden canónico."""
    reasons = set(selection.reasons)
    if length_tie:
        reasons.add(UnverifiedReason.LOW_AGREEMENT)
    if n < policy.min_readings:
        reasons.add(UnverifiedReason.INSUFFICIENT_READINGS)
    if selection.confidence < policy.confirm_threshold:
        reasons.add(UnverifiedReason.LOW_CONFIDENCE)
    if selection.agreement < policy.min_agreement:
        reasons.add(UnverifiedReason.LOW_AGREEMENT)
    return tuple(reason for reason in UnverifiedReason if reason in reasons)


def _require_unit_interval(value: float, name: str) -> None:
    """Exige un valor finito dentro de [0, 1]."""
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise InvalidEntityError(f"{name} fuera de [0, 1]: {value}")
