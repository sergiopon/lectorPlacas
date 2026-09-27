from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.errors import ConfigurationError
from tests.fixtures.fakes import (
    START,
    FakeClock,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)


class FakeTrainingStore:
    def __init__(self, deleted: int) -> None:
        self.deleted = deleted
        self.cutoffs: list[datetime] = []

    def write_samples(self, samples, created_at: datetime) -> Path:  # type: ignore[no-untyped-def]
        return Path("x")

    def delete_older_than(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return self.deleted


def purge(store: FakeTrainingStore | None, policy: RetentionPolicy) -> PurgeExpiredData:
    return PurgeExpiredData(
        InMemoryPlateRepository(),
        InMemoryCropStore(),
        InMemoryExportStore(),
        FakeClock(),
        policy,
        training_store=store,
    )


def test_purge_deletes_expired_training_exports() -> None:
    store = FakeTrainingStore(3)
    use_case = purge(store, RetentionPolicy(30, 90, 180))
    result = use_case.execute()
    assert result.training_deleted == 3
    assert store.cutoffs == [START - timedelta(days=180)]


def test_purge_without_training_store_and_default_policy() -> None:
    assert purge(None, RetentionPolicy(30, 90)).execute().training_deleted == 0
    assert RetentionPolicy(30, 90).training_days == 180


def test_invalid_training_days() -> None:
    with pytest.raises(ConfigurationError):
        RetentionPolicy(30, 90, 0)


def test_audit_detail_includes_training_count() -> None:
    repo = InMemoryPlateRepository()
    PurgeExpiredData(
        repo,
        InMemoryCropStore(),
        InMemoryExportStore(),
        FakeClock(),
        RetentionPolicy(30, 90),
        training_store=FakeTrainingStore(2),
    ).execute()
    assert repo.events[-1][2].endswith("entrenamiento=2")
