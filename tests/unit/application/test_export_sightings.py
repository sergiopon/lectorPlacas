from __future__ import annotations

from lector_placas.application.export_sightings import PAGE_SIZE, ExportSightings
from lector_placas.application.ports import AuditEvent, RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from tests.fixtures.fakes import START, FakeClock, InMemoryExportStore, InMemoryPlateRepository

UNVERIFIED = ConsolidatedPlate(
    "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


def test_exports_all_pages_and_audits() -> None:
    repo, store = InMemoryPlateRepository(), InMemoryExportStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track in range(PAGE_SIZE + 3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, UNVERIFIED, None, START))
    path = ExportSightings(repo, store, FakeClock()).execute(ReviewStatus.UNVERIFIED)
    assert len(store.written[0][0]) == PAGE_SIZE + 3
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.EXPORT
    assert detail == f"filas={PAGE_SIZE + 3} archivo={path.name}"
