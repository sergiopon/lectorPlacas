from __future__ import annotations

from datetime import datetime, timedelta

from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from tests.fixtures.fakes import (
    START,
    FakeClock,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)


class FakeStore:
    def __init__(self, deleted: int) -> None:
        self.deleted = deleted
        self.cutoffs: list[datetime] = []

    def delete_older_than(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return self.deleted


def purge(
    training: FakeStore | None = None, legibility: FakeStore | None = None
) -> PurgeExpiredData:
    return PurgeExpiredData(
        InMemoryPlateRepository(),
        InMemoryCropStore(),
        InMemoryExportStore(),
        FakeClock(),
        RetentionPolicy(30, 90, 180),
        training_store=training,
        legibility_store=legibility,
    )


def test_purge_adds_legibility_to_training_count() -> None:
    repo = InMemoryPlateRepository()
    training, legibility = FakeStore(2), FakeStore(3)
    result = PurgeExpiredData(
        repo,
        InMemoryCropStore(),
        InMemoryExportStore(),
        FakeClock(),
        RetentionPolicy(30, 90, 180),
        training_store=training,
        legibility_store=legibility,
    ).execute()

    assert result.training_deleted == 5
    cutoff = START - timedelta(days=180)
    assert training.cutoffs == [cutoff] and legibility.cutoffs == [cutoff]
    assert repo.events[-1][2].endswith("entrenamiento=5")


def test_purge_without_legibility_store() -> None:
    result = purge(training=FakeStore(2)).execute()
    assert result.training_deleted == 2
