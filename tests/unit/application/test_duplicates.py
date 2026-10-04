"""Tests de aceptación de `find_duplicates` (spec 061)."""

from __future__ import annotations

from lector_placas.application.duplicates import DuplicateCandidate, find_duplicates
from lector_placas.domain.entities import ReviewStatus

UNV = ReviewStatus.UNVERIFIED
CONF = ReviewStatus.CONFIRMED


def cand(
    sighting_id: int, text: str, status: ReviewStatus, confidence: float, start: int, end: int
) -> DuplicateCandidate:
    return DuplicateCandidate(sighting_id, text, status, confidence, start, end)


def test_confirmed_wins_and_window_splits() -> None:
    candidates = [
        cand(1, "ABC123", UNV, 0.8, 0, 1000),
        cand(2, "ABC123", CONF, 0.7, 5000, 6000),
        cand(3, "ABC123", UNV, 0.9, 40000, 41000),
    ]
    assert find_duplicates(candidates, 30000) == [(1, 2)]


def test_overlap_groups_and_higher_confidence_wins() -> None:
    candidates = [
        cand(4, "XYZ98K", UNV, 0.6, 0, 3000),
        cand(5, "XYZ98K", UNV, 0.9, 1000, 2000),
    ]
    assert find_duplicates(candidates, 30000) == [(4, 5)]


def test_tie_keeps_lowest_id() -> None:
    candidates = [
        cand(6, "DEF456", UNV, 0.5, 0, 100),
        cand(7, "DEF456", UNV, 0.5, 200, 300),
    ]
    assert find_duplicates(candidates, 30000) == [(7, 6)]


def test_group_end_is_max_of_members() -> None:
    candidates = [
        cand(8, "GHI789", UNV, 0.5, 0, 10000),
        cand(9, "GHI789", UNV, 0.6, 2000, 3000),
        cand(10, "GHI789", UNV, 0.7, 35000, 36000),
    ]
    assert find_duplicates(candidates, 30000) == [(8, 10), (9, 10)]


def test_different_texts_never_group() -> None:
    candidates = [
        cand(11, "ABC123", UNV, 0.5, 0, 100),
        cand(12, "ABC124", UNV, 0.5, 0, 100),
    ]
    assert find_duplicates(candidates, 30000) == []


def test_empty_and_single() -> None:
    assert find_duplicates([], 30000) == []
    assert find_duplicates([cand(1, "ABC123", UNV, 0.5, 0, 100)], 30000) == []
