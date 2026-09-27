from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.application.ports import (
    RunStart,
    RunStats,
    RunStatus,
    SightingQuery,
    VideoInfo,
)
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import RepositoryError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration

T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
INFO = VideoInfo(1920, 1080, 0, 60_000, 30.0, "h264")


@dataclass
class Seed:
    """Repositorio sembrado con dos corridas y cinco avistamientos."""

    repo: SqlCipherPlateRepository
    finished_run: int
    running_run: int
    abc_first: int
    abd: int
    xyz: int
    xab: int
    abc_second: int


def _confirmed(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(
        text, 0.97, 1.0, 3, ReviewStatus.CONFIRMED, (), ("co_particular_publico",)
    )


def _unverified(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(
        text,
        0.5,
        0.5,
        2,
        ReviewStatus.UNVERIFIED,
        (UnverifiedReason.LOW_CONFIDENCE,),
        ("co_particular_publico",),
    )


def _sighting(run_id: int, track: int, plate: ConsolidatedPlate, at: datetime) -> Sighting:
    return Sighting(run_id, track, 100, 900, VehicleType.CAR, plate, None, at)


def _seed(tmp_path: Path) -> Seed:
    repo = SqlCipherPlateRepository(tmp_path / "lector.db", FakeKeyProvider())
    finished_run = repo.start_run(RunStart("f" * 64, "calle_lenta", INFO, T0))
    repo.finish_run(finished_run, RunStats(10, 5, 2, 1, 1, 0, 1000, 60_000), T0 + HOUR, True)
    running_run = repo.start_run(RunStart("e" * 64, "parqueadero", INFO, T0 + 2 * HOUR))
    return Seed(
        repo=repo,
        finished_run=finished_run,
        running_run=running_run,
        abc_first=repo.save_sighting(_sighting(finished_run, 1, _confirmed("ABC123"), T0 + HOUR)),
        abd=repo.save_sighting(_sighting(finished_run, 2, _unverified("ABD456"), T0 + 2 * HOUR)),
        xyz=repo.save_sighting(_sighting(finished_run, 3, _unverified("XYZ9BK"), T0 + 3 * HOUR)),
        xab=repo.save_sighting(_sighting(running_run, 1, _confirmed("XAB123"), T0 + 4 * HOUR)),
        abc_second=repo.save_sighting(
            _sighting(running_run, 2, _confirmed("ABC123"), T0 + 5 * HOUR)
        ),
    )


def test_search_without_filters_returns_all_descending(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    records = browser.search_sightings(SightingQuery(), 100, 0)
    assert [r.sighting_id for r in records] == [
        seed.abc_second,
        seed.xab,
        seed.xyz,
        seed.abd,
        seed.abc_first,
    ]
    seed.repo.close()


def test_search_filters_by_status(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    confirmed_rows = browser.search_sightings(SightingQuery(status=ReviewStatus.CONFIRMED), 100, 0)
    assert [r.sighting_id for r in confirmed_rows] == [
        seed.abc_second,
        seed.xab,
        seed.abc_first,
    ]
    unverified_rows = browser.search_sightings(
        SightingQuery(status=ReviewStatus.UNVERIFIED), 100, 0
    )
    assert [r.sighting_id for r in unverified_rows] == [seed.xyz, seed.abd]
    seed.repo.close()


def test_search_filters_by_prefix(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    prefixed = browser.search_sightings(SightingQuery(plate_prefix="AB"), 100, 0)
    assert [r.sighting_id for r in prefixed] == [seed.abc_second, seed.abd, seed.abc_first]
    assert seed.xab not in [r.sighting_id for r in prefixed]
    anchored = browser.search_sightings(SightingQuery(plate_prefix="XAB"), 100, 0)
    assert [r.sighting_id for r in anchored] == [seed.xab]
    seed.repo.close()


def test_search_filters_by_run(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    first = browser.search_sightings(SightingQuery(run_id=seed.finished_run), 100, 0)
    assert [r.sighting_id for r in first] == [seed.xyz, seed.abd, seed.abc_first]
    second = browser.search_sightings(SightingQuery(run_id=seed.running_run), 100, 0)
    assert [r.sighting_id for r in second] == [seed.abc_second, seed.xab]
    seed.repo.close()


def test_search_filters_by_date_range(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    query = SightingQuery(created_from=T0 + 2 * HOUR, created_to=T0 + 4 * HOUR)
    rows = browser.search_sightings(query, 100, 0)
    assert [r.sighting_id for r in rows] == [seed.xyz, seed.abd]
    seed.repo.close()


def test_search_combines_filters(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    query = SightingQuery(status=ReviewStatus.CONFIRMED, plate_prefix="AB", run_id=seed.running_run)
    rows = browser.search_sightings(query, 100, 0)
    assert [r.sighting_id for r in rows] == [seed.abc_second]
    seed.repo.close()


def test_prefix_uses_corrected_text(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    original = browser.search_sightings(SightingQuery(plate_prefix="XYZ9B"), 100, 0)
    assert [r.sighting_id for r in original] == [seed.xyz]
    seed.repo.record_review(seed.xyz, ReviewStatus.CORRECTED, "XYZ98K", T0 + 6 * HOUR)
    corrected = browser.search_sightings(SightingQuery(plate_prefix="XYZ"), 100, 0)
    assert [r.sighting_id for r in corrected] == [seed.xyz]
    assert browser.search_sightings(SightingQuery(plate_prefix="XYZ9B"), 100, 0) == []
    seed.repo.close()


def test_count_matches_search_without_pagination(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    queries = [
        SightingQuery(),
        SightingQuery(status=ReviewStatus.CONFIRMED),
        SightingQuery(plate_prefix="AB"),
        SightingQuery(run_id=seed.finished_run),
        SightingQuery(created_from=T0 + 2 * HOUR, created_to=T0 + 4 * HOUR),
    ]
    for query in queries:
        assert browser.count_sightings(query) == len(browser.search_sightings(query, 100, 0))
    seed.repo.close()


def test_pagination_limit_offset(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    rows = browser.search_sightings(SightingQuery(), 2, 1)
    assert [r.sighting_id for r in rows] == [seed.xab, seed.xyz]
    seed.repo.close()


def test_invalid_pagination_raises(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    for limit, offset in ((0, 0), (10_001, 0), (10, -1)):
        with pytest.raises(RepositoryError):
            browser.search_sightings(SightingQuery(), limit, offset)
        with pytest.raises(RepositoryError):
            browser.list_runs(limit, offset)
    seed.repo.close()


def test_list_runs_descending_with_status_and_stats(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    runs = browser.list_runs(10, 0)
    assert [r.run_id for r in runs] == [seed.running_run, seed.finished_run]
    running, finished = runs
    assert running.status is RunStatus.RUNNING
    assert running.finished_at is None
    assert running.sightings_confirmed is None
    assert finished.status is RunStatus.COMPLETED
    assert finished.finished_at == T0 + HOUR
    assert finished.duration_ms == INFO.duration_ms
    assert (
        finished.frames_processed,
        finished.sightings_confirmed,
        finished.sightings_unverified,
    ) == (5, 1, 1)
    assert finished.tracks_without_reading == 0
    assert finished.processing_ms == 1000
    seed.repo.close()


def test_browser_after_close_raises_repository_error(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    browser = seed.repo.browser()
    seed.repo.close()
    with pytest.raises(RepositoryError):
        browser.search_sightings(SightingQuery(), 10, 0)
    with pytest.raises(RepositoryError):
        browser.count_sightings(SightingQuery())
    with pytest.raises(RepositoryError):
        browser.list_runs(10, 0)
