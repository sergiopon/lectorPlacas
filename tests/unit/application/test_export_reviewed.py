from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from lector_placas.application.export_reviewed import ExportReviewedCrops
from lector_placas.application.ports import AuditEvent, ImageBGR, RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository


class FakeTrainingStore:
    def __init__(self) -> None:
        self.samples: list[tuple[str, ImageBGR]] = []

    def write_samples(self, samples, created_at: datetime) -> Path:  # type: ignore[no-untyped-def]
        self.samples = list(samples)
        return Path("reviewed-20260926T120000Z")

    def delete_older_than(self, cutoff: datetime) -> int:
        return 0


def confirmed(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(text, 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())


def unverified(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(
        text, 0.4, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
    )


def test_exports_confirmed_and_corrected_only() -> None:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))

    def add(track: int, plate: ConsolidatedPlate, crop_ref: str | None) -> int:
        return repo.save_sighting(
            Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, crop_ref, START)
        )

    add(1, confirmed("ABC123"), crops.save(np.full((10, 30, 3), 1, np.uint8)))
    corrected_id = add(2, unverified("XYZ98K"), crops.save(np.full((10, 30, 3), 2, np.uint8)))
    repo.record_review(corrected_id, ReviewStatus.CORRECTED, "XYZ98L", START)
    add(3, unverified("DEF456"), crops.save(np.full((10, 30, 3), 3, np.uint8)))
    add(4, confirmed("GHI789"), "f" * 32)
    add(5, confirmed("JKL012"), None)

    store = FakeTrainingStore()
    result = ExportReviewedCrops(repo, crops, store, FakeClock()).execute()

    assert [text for text, _ in store.samples] == ["ABC123", "XYZ98L"]
    assert [int(image[0, 0, 0]) for _, image in store.samples] == [1, 2]
    assert (result.exported, result.skipped, result.path.name) == (
        2,
        2,
        "reviewed-20260926T120000Z",
    )
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.EXPORT
    assert "filas=2" in detail and "omitidos=2" in detail
    assert "ABC" not in detail and "XYZ" not in detail
