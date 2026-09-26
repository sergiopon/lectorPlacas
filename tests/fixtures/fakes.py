from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lector_placas.application.ports import (
    AuditEvent,
    ImageBGR,
    RecordPurge,
    RunStart,
    RunStats,
)
from lector_placas.domain.entities import ReviewStatus, Sighting, SightingRecord
from lector_placas.domain.errors import CropNotFoundError, SightingNotFoundError

START = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
LINKED = (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED)


class FakeClock:
    def __init__(self, start: datetime = START, step_ms: int = 0) -> None:
        self.current = start
        self.step = timedelta(milliseconds=step_ms)

    def now(self) -> datetime:
        value = self.current
        self.current = self.current + self.step
        return value


class FakeKeyProvider:
    def __init__(self, key: bytes = bytes(range(32))) -> None:
        self.key = key

    def master_key(self) -> bytes:
        return self.key


class InMemoryCropStore:
    def __init__(self) -> None:
        self.images: dict[str, ImageBGR] = {}
        self.swept_before: list[datetime] = []
        self._counter = itertools.count(1)

    def save(self, image: ImageBGR) -> str:
        ref = f"{next(self._counter):032x}"
        self.images[ref] = image.copy()
        return ref

    def load(self, crop_ref: str) -> ImageBGR:
        if crop_ref not in self.images:
            raise CropNotFoundError("recorte no encontrado")
        return self.images[crop_ref].copy()

    def delete(self, crop_ref: str) -> None:
        self.images.pop(crop_ref, None)

    def delete_older_than(self, cutoff: datetime) -> int:
        self.swept_before.append(cutoff)
        return 0


class InMemoryExportStore:
    def __init__(self, files_to_delete: int = 0) -> None:
        self.written: list[tuple[tuple[SightingRecord, ...], datetime]] = []
        self.deleted_before: list[datetime] = []
        self.files_to_delete = files_to_delete

    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path:
        self.written.append((tuple(records), created_at))
        return Path(f"sightings-{len(self.written)}.csv")

    def delete_older_than(self, cutoff: datetime) -> int:
        self.deleted_before.append(cutoff)
        return self.files_to_delete


@dataclass
class StoredRun:
    start: RunStart
    stats: RunStats | None = None
    finished_at: datetime | None = None
    succeeded: bool | None = None


class InMemoryPlateRepository:
    def __init__(self) -> None:
        self.runs: dict[int, StoredRun] = {}
        self.records: dict[int, SightingRecord] = {}
        self.plates: set[str] = set()
        self.events: list[tuple[AuditEvent, datetime, str]] = []
        self.closed = False
        self._run_ids = itertools.count(1)
        self._sighting_ids = itertools.count(1)

    def start_run(self, run: RunStart) -> int:
        run_id = next(self._run_ids)
        self.runs[run_id] = StoredRun(run)
        self.log_event(AuditEvent.RUN_STARTED, run.started_at, f"run_id={run_id}")
        return run_id

    def finish_run(
        self, run_id: int, stats: RunStats, finished_at: datetime, succeeded: bool
    ) -> None:
        run = self.runs[run_id]
        run.stats, run.finished_at, run.succeeded = stats, finished_at, succeeded
        status = "completed" if succeeded else "failed"
        self.log_event(AuditEvent.RUN_FINISHED, finished_at, f"run_id={run_id} status={status}")

    def save_sighting(self, sighting: Sighting) -> int:
        sighting_id = next(self._sighting_ids)
        plate = sighting.plate
        self.records[sighting_id] = SightingRecord(
            sighting_id,
            sighting.run_id,
            sighting.track_id,
            sighting.first_seen_ms,
            sighting.last_seen_ms,
            sighting.vehicle_type,
            plate.text,
            plate.text,
            plate.confidence,
            plate.agreement,
            plate.num_readings,
            plate.status,
            plate.reasons,
            plate.format_ids,
            sighting.crop_ref,
            sighting.created_at,
            None,
        )
        if plate.status is ReviewStatus.CONFIRMED:
            self.plates.add(plate.text)
        return sighting_id

    def list_sightings(
        self, status: ReviewStatus | None, limit: int, offset: int
    ) -> list[SightingRecord]:
        rows = [r for _, r in sorted(self.records.items()) if status is None or r.status is status]
        return rows[offset : offset + limit]

    def get_sighting(self, sighting_id: int) -> SightingRecord:
        if sighting_id not in self.records:
            raise SightingNotFoundError(f"sighting_id={sighting_id}")
        return self.records[sighting_id]

    def record_review(
        self,
        sighting_id: int,
        status: ReviewStatus,
        corrected_text: str | None,
        reviewed_at: datetime,
    ) -> None:
        record = self.get_sighting(sighting_id)
        text = corrected_text if corrected_text is not None else record.plate_text
        self.records[sighting_id] = replace(
            record, status=status, plate_text=text, reviewed_at=reviewed_at
        )
        if status in LINKED:
            self.plates.add(text)

    def expire_crop_refs(self, cutoff: datetime) -> list[str]:
        refs: list[str] = []
        for sighting_id, record in sorted(self.records.items()):
            if record.created_at < cutoff and record.crop_ref is not None:
                refs.append(record.crop_ref)
                self.records[sighting_id] = replace(record, crop_ref=None)
        return refs

    def delete_records_before(self, cutoff: datetime) -> RecordPurge:
        old = sorted(sid for sid, r in self.records.items() if r.created_at < cutoff)
        refs = tuple(ref for sid in old if (ref := self.records[sid].crop_ref) is not None)
        for sighting_id in old:
            del self.records[sighting_id]
        live_runs = {r.run_id for r in self.records.values()}
        dead_runs = [
            rid
            for rid, run in self.runs.items()
            if run.start.started_at < cutoff and rid not in live_runs
        ]
        for run_id in dead_runs:
            del self.runs[run_id]
        live_texts = {r.plate_text for r in self.records.values() if r.status in LINKED}
        dead_plates = self.plates - live_texts
        self.plates -= dead_plates
        return RecordPurge(len(old), len(dead_runs), len(dead_plates), refs)

    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None:
        self.events.append((event, occurred_at, detail))

    def close(self) -> None:
        self.closed = True
