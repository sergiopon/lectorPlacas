"""Detección de avistamientos duplicados de la misma placa dentro de una corrida (spec 061)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lector_placas.domain.entities import ReviewStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

MIN_GROUP_SIZE: Final[int] = 2


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    """Avistamiento guardado que participa en la búsqueda de duplicados."""

    sighting_id: int
    plate_text: str
    status: ReviewStatus
    confidence: float
    first_seen_ms: int
    last_seen_ms: int


def _keeper_key(candidate: DuplicateCandidate) -> tuple[int, float, int]:
    """Clave de elección del conservado: confirmado, mayor confianza, menor id."""
    return (
        0 if candidate.status is ReviewStatus.CONFIRMED else 1,
        -candidate.confidence,
        candidate.sighting_id,
    )


def _split_groups(
    ordered: Sequence[DuplicateCandidate], window_ms: int
) -> list[list[DuplicateCandidate]]:
    """Forma grupos de candidatos cercanos en el tiempo (ya ordenados por inicio e id)."""
    groups: list[list[DuplicateCandidate]] = []
    end = 0
    for candidate in ordered:
        if groups and candidate.first_seen_ms - end <= window_ms:
            groups[-1].append(candidate)
            end = max(end, candidate.last_seen_ms)
        else:
            groups.append([candidate])
            end = candidate.last_seen_ms
    return groups


def find_duplicates(
    candidates: Sequence[DuplicateCandidate], window_ms: int
) -> list[tuple[int, int]]:
    """Devuelve pares (id del duplicado, id del conservado), ordenados por el primer elemento.

    Args:
        candidates: avistamientos de una corrida.
        window_ms: separación máxima en ms entre un candidato y el fin del grupo abierto.

    Returns:
        Pares `(sighting_id del duplicado, sighting_id del conservado)`.
    """
    by_text: dict[str, list[DuplicateCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_text[candidate.plate_text].append(candidate)
    pairs: list[tuple[int, int]] = []
    for same_text in by_text.values():
        ordered = sorted(same_text, key=lambda c: (c.first_seen_ms, c.sighting_id))
        for group in _split_groups(ordered, window_ms):
            if len(group) < MIN_GROUP_SIZE:
                continue
            keeper = min(group, key=_keeper_key)
            pairs.extend((c.sighting_id, keeper.sighting_id) for c in group if c is not keeper)
    return sorted(pairs, key=lambda pair: pair[0])
