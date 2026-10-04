from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from lector_placas.application import export_legibility
from lector_placas.application.export_legibility import ExportLegibilityDataset
from lector_placas.application.ports import (
    AuditEvent,
    ImageBGR,
    LegibilityLabel,
    LegibilitySample,
    RunStart,
    VideoInfo,
)
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

HASH_A = "a" * 64
HASH_B = "b" * 64
INFO = VideoInfo(1920, 1080, 0, None, None, "h264")
PLATES = ("ABC123", "XYZ98K")


class FakeLegibilityStore:
    def __init__(self) -> None:
        self.samples: list[LegibilitySample] = []
        self.created_at: datetime | None = None

    def write_samples(self, samples: Sequence[LegibilitySample], created_at: datetime) -> Path:
        self.samples = list(samples)
        self.created_at = created_at
        return Path("legibility-20260926T120000Z")

    def delete_older_than(self, cutoff: datetime) -> int:
        return 0


def confirmed(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(text, 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())


def unverified(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(
        text, 0.4, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
    )


def crop(value: int) -> ImageBGR:
    return np.full((10, 30, 3), value, np.uint8)


def add(
    repo: InMemoryPlateRepository,
    run_id: int,
    track: int,
    plate: ConsolidatedPlate,
    crop_ref: str | None,
) -> int:
    return repo.save_sighting(
        Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, crop_ref, START)
    )


def execute(
    repo: InMemoryPlateRepository, crops: InMemoryCropStore, store: FakeLegibilityStore
) -> tuple[export_legibility.ExportLegibilityResult, FakeLegibilityStore]:
    result = ExportLegibilityDataset(repo, crops, store, FakeClock()).execute()
    return result, store


def test_exports_final_statuses_with_labels() -> None:
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    add(repo, run_id, 1, confirmed("ABC123"), crops.save(crop(1)))
    corrected = add(repo, run_id, 2, unverified("XYZ98K"), crops.save(crop(2)))
    repo.record_review(corrected, ReviewStatus.CORRECTED, "XYZ98L", START)
    illegible = add(repo, run_id, 3, confirmed("DEF456"), crops.save(crop(3)))
    repo.record_review(illegible, ReviewStatus.ILLEGIBLE, None, START)
    rejected = add(repo, run_id, 4, confirmed("GHI789"), crops.save(crop(4)))
    repo.record_review(rejected, ReviewStatus.REJECTED, None, START)
    add(repo, run_id, 5, unverified("JKL012"), crops.save(crop(5)))

    result, store = execute(repo, crops, store)

    assert [sample.label for sample in store.samples] == [
        LegibilityLabel.LEGIBLE,
        LegibilityLabel.LEGIBLE,
        LegibilityLabel.BLURRY,
        LegibilityLabel.NOT_PLATE,
    ]
    assert [int(sample.image[0, 0, 0]) for sample in store.samples] == [1, 2, 3, 4]
    assert result.exported == 4 and result.skipped == 0
    assert result.per_label == {
        LegibilityLabel.LEGIBLE: 2,
        LegibilityLabel.BLURRY: 1,
        LegibilityLabel.NOT_PLATE: 1,
    }
    assert all(sample.status is not ReviewStatus.UNVERIFIED for sample in store.samples)


def test_human_reviewed_flag() -> None:
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    add(repo, run_id, 1, confirmed("ABC123"), crops.save(crop(1)))
    reviewed = add(repo, run_id, 2, confirmed("DEF456"), crops.save(crop(2)))
    repo.record_review(reviewed, ReviewStatus.CONFIRMED, None, START)

    _, store = execute(repo, crops, store)

    assert [sample.human_reviewed for sample in store.samples] == [False, True]


def test_skips_missing_crops() -> None:
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    add(repo, run_id, 1, confirmed("ABC123"), crops.save(crop(1)))
    add(repo, run_id, 2, confirmed("DEF456"), None)
    add(repo, run_id, 3, confirmed("GHI789"), "f" * 32)

    result, store = execute(repo, crops, store)

    assert result.exported == 1 and result.skipped == 2
    assert [int(sample.image[0, 0, 0]) for sample in store.samples] == [1]


def test_video_groups_follow_first_run() -> None:
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    first = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    second = repo.start_run(RunStart(HASH_B, "p", INFO, START))
    third = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    add(repo, first, 1, confirmed("ABC123"), crops.save(crop(1)))
    add(repo, second, 2, confirmed("DEF456"), crops.save(crop(2)))
    add(repo, third, 3, confirmed("GHI789"), crops.save(crop(3)))

    _, store = execute(repo, crops, store)

    groups = {sample.run_id: sample.video_group for sample in store.samples}
    assert groups[first] == 1 and groups[third] == 1 and groups[second] == 2


def test_audit_and_log_without_plate_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    add(repo, run_id, 1, confirmed(PLATES[0]), crops.save(crop(1)))
    add(repo, run_id, 2, confirmed(PLATES[1]), crops.save(crop(2)))

    result, _ = execute(repo, crops, store)

    event, _, detail = repo.events[-1]
    assert event is AuditEvent.EXPORT
    for fragment in (
        "filas=",
        "omitidos=",
        "legibles=",
        "borrosas=",
        "no_placa=",
        result.path.name,
    ):
        assert fragment in detail
        assert fragment in caplog.text
    for secret in (*PLATES, HASH_A, HASH_B):
        assert secret not in detail
        assert secret not in caplog.text


def test_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_legibility, "PAGE_SIZE", 2)
    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(RunStart(HASH_A, "p", INFO, START))
    for track in range(5):
        add(repo, run_id, track, confirmed(f"ABC{track:03d}"), crops.save(crop(track)))

    result, _ = execute(repo, crops, store)

    assert result.exported == 5 and len(store.samples) == 5


def _verify_quality_export(samples: list[LegibilitySample], run_id: int) -> None:
    """Verifica que las muestras tienen calidad y tamaño de frame."""
    # Primera muestra con calidad
    sample_with_quality = next(s for s in samples if s.run_id == run_id and s.track_id == 0)
    assert sample_with_quality.plate_width_px == 100
    assert sample_with_quality.plate_height_px == 30
    assert sample_with_quality.sharpness == 12.5
    assert sample_with_quality.contrast == 40.0
    assert sample_with_quality.frame_width == 1920
    assert sample_with_quality.frame_height == 1080

    # Segunda muestra sin calidad
    sample_without_quality = next(s for s in samples if s.run_id == run_id and s.track_id == 1)
    assert sample_without_quality.plate_width_px is None
    assert sample_without_quality.plate_height_px is None
    assert sample_without_quality.sharpness is None
    assert sample_without_quality.contrast is None
    assert sample_without_quality.frame_width == 1920
    assert sample_without_quality.frame_height == 1080


def test_exports_quality_and_frame_size() -> None:
    """Las muestras incluyen calidad y tamaño del frame."""
    from lector_placas.domain.entities import CropQuality

    repo, crops, store = InMemoryPlateRepository(), InMemoryCropStore(), FakeLegibilityStore()
    run_id = repo.start_run(
        RunStart(HASH_A, "p", VideoInfo(1920, 1080, 0, None, None, "h264"), START)
    )

    # Guardar un avistamiento con calidad
    sighting_with_quality = Sighting(
        run_id,
        0,
        0,
        1,
        VehicleType.CAR,
        confirmed("ABC123"),
        crops.save(crop(1)),
        START,
        CropQuality(100, 30, 12.5, 40.0),
    )
    repo.save_sighting(sighting_with_quality)

    # Guardar un avistamiento sin calidad
    sighting_without_quality = Sighting(
        run_id,
        1,
        1,
        1,
        VehicleType.CAR,
        confirmed("DEF456"),
        crops.save(crop(2)),
        START,
        None,
    )
    repo.save_sighting(sighting_without_quality)

    result, store = execute(repo, crops, store)

    assert result.exported == 2
    samples = store.samples
    _verify_quality_export(samples, run_id)
