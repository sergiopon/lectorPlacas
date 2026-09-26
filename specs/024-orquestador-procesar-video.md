# 024 - Aplicación: caso de uso ProcessVideo (orquestador)

## Objetivo
Implementar `ProcessVideo`, que recorre el video, detecta, sigue, lee placas dirigidas por track,
consolida los tracks finalizados y persiste los avistamientos, dependiendo solo de puertos.

## Depende de
004, 005, 009, 023.

## Archivos rectores aplicables
- ARQUITECTURA.md §3 (flujo normativo), §2 (DIP: solo Protocols), §6. ADR-006, ADR-007, ADR-013.
- docs/02-contratos.md §5 y §7 (estrategia de errores). reglas-seguridad.md SEG-05 (logs con `mask_plate`).

## Archivos a crear/modificar
- `src/lector_placas/application/process_video.py`
- `tests/unit/application/test_process_video.py`

## Dependencias externas
numpy==2.5.3.

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005) — ver CONTEXT.md para todas las firmas
Frame, VideoInfo, RunStart, RunStats, ImageBGR, VideoSourceFactory, VideoSource, FrameSampler,
VehicleDetector, PlateDetector, Tracker, PlateReader, ImageQualityScorer, PlateConsolidator,
PlateRepository, CropStore, Clock
# de application/track_registry.py (spec 023)
class FinalizedTrack: track_id; first_seen_ms; last_seen_ms; vehicle_type; readings: tuple[PlateReading, ...]; best_crop: ImageBGR | None
class TrackRegistry:
    def __init__(self, max_readings_per_track: int) -> None: ...
    def observe(self, tracked: Sequence[TrackedVehicle], timestamp_ms: int) -> None: ...
    def needs_reading(self, track_id: int) -> bool: ...
    def add_reading(self, reading: PlateReading, crop: ImageBGR) -> None: ...
    def pop_inactive(self, now_ms: int, inactive_after_ms: int) -> list[FinalizedTrack]: ...
    def pop_all(self) -> list[FinalizedTrack]: ...
# de application/image_ops.py (spec 023)
def crop_image(image: ImageBGR, box: BoundingBox) -> ImageBGR: ...
# de domain: BoundingBox (expand, translate, clip, width, height, area), PlateReading, Sighting,
#   ReviewStatus, LectorPlacasError, InvalidEntityError; domain/privacy.mask_plate
```
```python
# application/process_video.py — a implementar
MIN_VEHICLE_CROP_PX: Final[int] = 16

@dataclass(frozen=True, slots=True)
class ProcessingSettings:
    profile_name: str
    max_ocr_per_frame: int
    min_plate_width_px: int
    min_sharpness: float
    vehicle_crop_margin: float
    track_finalize_after_ms: int
    max_readings_per_track: int

@dataclass(frozen=True, slots=True)
class PipelineDependencies:
    source_factory: VideoSourceFactory
    sampler: FrameSampler
    vehicle_detector: VehicleDetector
    plate_detector: PlateDetector
    tracker: Tracker
    reader: PlateReader
    quality: ImageQualityScorer
    consolidator: PlateConsolidator
    repository: PlateRepository
    crop_store: CropStore
    clock: Clock

@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: int
    stats: RunStats

class ProcessVideo:
    def __init__(self, deps: PipelineDependencies, settings: ProcessingSettings) -> None: ...
    def execute(self, video_path: Path, video_sha256: str) -> RunResult: ...
```

## Comportamiento esperado
1. `ProcessingSettings.__post_init__`: enteros ≥ 1, `min_sharpness >= 0`, `vehicle_crop_margin` en [0, 1],
   `profile_name` no vacío; si no → `InvalidEntityError`.
2. `execute(video_path, sha)`: `source = deps.source_factory.open(video_path)`; en `try/finally` se garantiza `source.close()`.
3. Inicio de corrida: `started = clock.now()` (**llamada 1 a `now`**); `info = source.info()`;
   `run_id = repository.start_run(RunStart(sha, settings.profile_name, info, started))`;
   `deps.tracker.reset()`; `deps.sampler.reset()`; `registry = TrackRegistry(settings.max_readings_per_track)`;
   contadores privados en una dataclass mutable `_Counters` (frames_decoded, frames_processed, tracks_total,
   sightings_confirmed, sightings_unverified, tracks_without_reading).
4. Por cada `frame` de `source.frames()`:
   1. `frames_decoded += 1`; si `not sampler.should_process(frame.timestamp_ms)` → siguiente frame.
   2. `frames_processed += 1`; `detections = vehicle_detector.detect(frame.image)`;
      `tracked = tracker.update(detections, frame.image, frame.timestamp_ms)`; `registry.observe(tracked, frame.timestamp_ms)`.
   3. Candidatos = `tracked` con `registry.needs_reading(track_id)`, ordenados por `box.area` descendente (estable),
      máximo `max_ocr_per_frame`.
   4. Para cada candidato, `_plate_candidate` (devuelve `None` en cuanto un paso falla):
      a. `vbox = tracked.box.expand(vehicle_crop_margin, frame.width, frame.height)`; `None` o
         `vbox.width < MIN_VEHICLE_CROP_PX` o `vbox.height < MIN_VEHICLE_CROP_PX` → `None`.
      b. `vehicle_crop = crop_image(frame.image, vbox)`; `plates = plate_detector.detect(vehicle_crop)`; vacío → `None`.
      c. `best = max(plates, key=confidence)` (el primero en caso de empate);
         `pbox = best.box.translate(floor(vbox.x1), floor(vbox.y1)).clip(frame.width, frame.height)`; `None` → `None`.
      d. `pbox.width < min_plate_width_px` → `None`.
      e. `plate_crop = crop_image(frame.image, pbox)`; `sharp = quality.sharpness(plate_crop)`; `sharp < min_sharpness` → `None`.
      f. Devuelve un `_PlateCandidate(track, pbox, best.confidence, plate_crop, sharp)` (dataclass privada).
   5. Si hay candidatos: `results = reader.read([c.crop for c in candidatos])` (una sola llamada por frame); para cada par
      con `result.text != ""`: `registry.add_reading(PlateReading(track_id, frame.index, frame.timestamp_ms, result.text,
      result.char_confidences, c.pbox, c.detection_confidence, c.sharpness), c.crop)`.
   6. `_finalize(registry.pop_inactive(frame.timestamp_ms, settings.track_finalize_after_ms))`.
5. Tras el último frame: `_finalize(registry.pop_all())`.
6. `_finalize(tracks)`: por cada track: `tracks_total += 1`; sin lecturas → `tracks_without_reading += 1` y continuar.
   Si no: `plate = consolidator.consolidate(track.readings, track.vehicle_type)`;
   `crop_ref = crop_store.save(track.best_crop)` si `best_crop` no es `None`;
   `repository.save_sighting(Sighting(run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, plate, crop_ref, clock.now()))`
   (**una llamada a `now` por avistamiento**); incrementa `sightings_confirmed` o `sightings_unverified`;
   `logger.info("avistamiento run_id=%d track_id=%d estado=%s placa=%s", ..., mask_plate(plate.text))`.
7. Fin exitoso: `finished = clock.now()` (**última llamada**); `processing_ms = int((finished - started).total_seconds() * 1000)`;
   `stats = RunStats(..., processing_ms, info.duration_ms)`; `repository.finish_run(run_id, stats, finished, True)`;
   `logger.info` con las estadísticas; devuelve `RunResult(run_id, stats)`.
8. Error: cualquier `LectorPlacasError` después de `start_run` → `finished = clock.now()`, `finish_run(run_id, stats_parciales, finished, False)`,
   `logger.error("corrida fallida run_id=%d error=%s", run_id, type(e).__name__)` y se relanza. Los tracks pendientes se descartan.
   Las funciones privadas respetan ≤ 20 sentencias (divide en `_process_frame`, `_collect_candidates`, `_plate_candidate`,
   `_record_readings`, `_finalize`, `_save_track`, `_stats`).

## Casos borde y manejo de errores
- Un resultado OCR vacío no crea lectura.
- Nunca se registra texto de placa sin `mask_plate`.

## Tests de aceptación
```python
# tests/unit/application/test_process_video.py
from __future__ import annotations

from collections.abc import Iterator
from itertools import cycle
from pathlib import Path

import numpy as np
import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.ports import Frame, VideoInfo
from lector_placas.application.process_video import (
    PipelineDependencies, ProcessingSettings, ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox, OcrResult, PlateDetection, ReviewStatus, TrackedVehicle, VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import InferenceError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository
from tests.fixtures.plate_catalog import build_test_catalog

SHA = "d" * 64
CAR_BOX = BoundingBox(100, 100, 300, 250)
PLATE_IN_CROP = BoundingBox(50, 100, 150, 130)


class FakeSource:
    def __init__(self, stamps: list[int]) -> None:
        self.stamps = stamps
        self.closed = False

    def info(self) -> VideoInfo:
        return VideoInfo(640, 480, 0, 1000, 10.0, "mpeg4")

    def frames(self) -> Iterator[Frame]:
        for index, stamp in enumerate(self.stamps):
            yield Frame(index, stamp, np.full((480, 640, 3), 90, np.uint8))

    def close(self) -> None:
        self.closed = True


class FakeSourceFactory:
    def __init__(self, source: FakeSource) -> None:
        self.source = source

    def open(self, path: Path) -> FakeSource:
        return self.source


class ScriptedVehicleDetector:
    def __init__(self, visible_calls: int | None = None, fail_on_call: int | None = None) -> None:
        self.visible_calls = visible_calls
        self.fail_on_call = fail_on_call
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[VehicleDetection]:
        call = self.calls
        self.calls += 1
        if call == self.fail_on_call:
            raise InferenceError("fallo sintético")
        if self.visible_calls is not None and call >= self.visible_calls:
            return []
        return [VehicleDetection(CAR_BOX, 0.9, VehicleType.CAR)]


class SingleTrackTracker:
    def __init__(self) -> None:
        self.resets = 0

    def update(self, detections, image, timestamp_ms):  # type: ignore[no-untyped-def]
        return [TrackedVehicle(0, d.box, d.confidence, d.vehicle_type) for d in detections]

    def reset(self) -> None:
        self.resets += 1


class FixedPlateDetector:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.shapes: list[tuple[int, ...]] = []

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        self.shapes.append(image.shape)
        return [PlateDetection(PLATE_IN_CROP, 0.9)] if self.found else []


class CyclingReader:
    def __init__(self, texts: list[str], conf: float = 0.95) -> None:
        self.texts = cycle(texts)
        self.conf = conf
        self.calls = 0

    def read(self, plate_images):  # type: ignore[no-untyped-def]
        self.calls += 1
        results = []
        for _ in plate_images:
            text = next(self.texts)
            results.append(OcrResult(text, (self.conf,) * len(text)))
        return results


class ConstantQuality:
    def sharpness(self, image: np.ndarray) -> float:
        return 50.0


def build(stamps: list[int], *, detector: ScriptedVehicleDetector | None = None,
          plates: FixedPlateDetector | None = None, reader: CyclingReader | None = None,
          target_fps: float = 10.0, min_plate_width_px: int = 20):  # type: ignore[no-untyped-def]
    source = FakeSource(stamps)
    parts = {
        "source": source, "tracker": SingleTrackTracker(), "repo": InMemoryPlateRepository(),
        "crops": InMemoryCropStore(), "detector": detector or ScriptedVehicleDetector(),
        "plates": plates or FixedPlateDetector(), "reader": reader or CyclingReader(["ABC123"]),
    }
    deps = PipelineDependencies(
        FakeSourceFactory(source), TimeBasedFrameSampler(target_fps), parts["detector"],
        parts["plates"], parts["tracker"], parts["reader"], ConstantQuality(),
        VotingPlateConsolidator(build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1),
                                ConfusionMap.default()),
        parts["repo"], parts["crops"], FakeClock(step_ms=10),
    )
    settings = ProcessingSettings("calle_lenta", 8, min_plate_width_px, 0.0, 0.10, 2000, 8)
    return ProcessVideo(deps, settings), parts


def test_happy_path_confirms_plate() -> None:
    process, parts = build([i * 100 for i in range(10)])
    result = process.execute(Path("v.mp4"), SHA)
    stats = result.stats
    assert result.run_id == 1
    assert (stats.frames_decoded, stats.frames_processed, stats.tracks_total) == (10, 10, 1)
    assert (stats.sightings_confirmed, stats.sightings_unverified, stats.tracks_without_reading) == (1, 0, 0)
    assert stats.processing_ms == 20
    assert stats.video_duration_ms == 1000
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert (record.plate_text, record.status, record.num_readings) == ("ABC123", ReviewStatus.CONFIRMED, 8)
    assert (record.first_seen_ms, record.last_seen_ms) == (0, 900)
    assert parts["reader"].calls == 8
    assert parts["plates"].shapes[0] == (180, 240, 3)
    assert next(iter(parts["crops"].images.values())).shape == (30, 100, 3)
    assert parts["repo"].runs[1].succeeded is True
    assert parts["source"].closed
    assert parts["tracker"].resets == 1


def test_inactive_track_is_finalized_during_video() -> None:
    process, parts = build([i * 100 for i in range(31)],
                           detector=ScriptedVehicleDetector(visible_calls=3))
    stats = process.execute(Path("v.mp4"), SHA).stats
    records = parts["repo"].list_sightings(None, 10, 0)
    assert len(records) == 1 and stats.tracks_total == 1
    assert (records[0].last_seen_ms, records[0].num_readings) == (200, 3)
    assert records[0].status is ReviewStatus.CONFIRMED


@pytest.mark.parametrize("kwargs", [
    {"plates": FixedPlateDetector(found=False)},
    {"min_plate_width_px": 200},
    {"reader": CyclingReader([""])},
])
def test_tracks_without_reading(kwargs: dict[str, object]) -> None:
    process, parts = build([0, 100, 200], **kwargs)  # type: ignore[arg-type]
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert (stats.tracks_total, stats.tracks_without_reading) == (1, 1)
    assert parts["repo"].list_sightings(None, 10, 0) == []


def test_disagreeing_readings_are_unverified() -> None:
    process, parts = build([i * 100 for i in range(10)],
                           reader=CyclingReader(["ABC123", "ABD123", "ABE123"]))
    stats = process.execute(Path("v.mp4"), SHA).stats
    record = parts["repo"].list_sightings(None, 10, 0)[0]
    assert stats.sightings_unverified == 1
    assert record.status is ReviewStatus.UNVERIFIED
    assert record.plate_text == "ABC123"


def test_error_marks_run_failed_and_closes_source() -> None:
    process, parts = build([i * 100 for i in range(10)],
                           detector=ScriptedVehicleDetector(fail_on_call=3))
    with pytest.raises(InferenceError):
        process.execute(Path("v.mp4"), SHA)
    assert parts["repo"].runs[1].succeeded is False
    assert parts["source"].closed
    assert parts["repo"].list_sightings(None, 10, 0) == []


def test_sampling_reduces_processed_frames() -> None:
    process, _ = build([round(i * 1000 / 30) for i in range(30)])
    stats = process.execute(Path("v.mp4"), SHA).stats
    assert (stats.frames_decoded, stats.frames_processed) == (30, 10)
```

## Fuera de alcance
Construcción de las dependencias reales (spec 028); purga previa (spec 025).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `process_video.py` solo importa `domain`, `application` y stdlib/numpy.
