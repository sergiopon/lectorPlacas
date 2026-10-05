"""Caso de uso `ProcessVideo`: orquesta el pipeline completo sobre un video (ARQUITECTURA.md §3)."""

from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from lector_placas.application.duplicates import DuplicateCandidate, find_duplicates
from lector_placas.application.image_ops import crop_image, rms_contrast
from lector_placas.application.legibility import (
    LegibilityModel,
    feature_vector,
    legibility_reason,
)
from lector_placas.application.ports import (
    Clock,
    CropStore,
    Frame,
    FrameSampler,
    ImageBGR,
    ImageQualityScorer,
    PlateConsolidator,
    PlateDetector,
    PlateReader,
    PlateRepository,
    ProgressReporter,
    ProgressUpdate,
    RunStart,
    RunStats,
    Tracker,
    VehicleDetector,
    VideoSource,
    VideoSourceFactory,
)
from lector_placas.application.proximity import (
    FULL_FRAME_ROI,
    NEAR_MIN_WIDTH_FRAC_MAX,
    ProximityCounters,
    center_in_roi,
    effective_min_width,
    touches_frame_edge,
    validate_roi,
)
from lector_placas.application.track_registry import FinalizedTrack, TrackRegistry
from lector_placas.domain.entities import (
    BoundingBox,
    ConsolidatedPlate,
    CropQuality,
    PlateDetection,
    PlateReading,
    ReviewStatus,
    Sighting,
    TrackedVehicle,
)
from lector_placas.domain.errors import (
    InvalidEntityError,
    LectorPlacasError,
    ProcessingCancelledError,
)
from lector_placas.domain.privacy import mask_plate

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

logger = logging.getLogger(__name__)

MIN_VEHICLE_CROP_PX: Final[int] = 16
DEDUP_WINDOW_MS_MAX: Final[int] = 600_000


@dataclass(frozen=True, slots=True)
class ProcessingSettings:
    """Parámetros del pipeline para un perfil de escenario (ADR-006)."""

    profile_name: str
    max_ocr_per_frame: int
    min_plate_width_px: int
    min_sharpness: float
    vehicle_crop_margin: float
    track_finalize_after_ms: int
    max_readings_per_track: int
    near_min_width_frac: float = 0.0
    max_plate_vehicle_ratio: float = 1.0
    roi: tuple[float, float, float, float] = FULL_FRAME_ROI
    early_stop: bool = False
    dedup_window_ms: int = 0
    legibility: LegibilityModel | None = None

    def __post_init__(self) -> None:
        """Valida los umbrales y límites del perfil.

        Raises:
            InvalidEntityError: si algún entero es menor que 1, `min_sharpness` es negativo,
                `vehicle_crop_margin` sale de [0, 1] o `profile_name` está vacío.
        """
        self._validate_core_settings()
        self._validate_proximity_settings()
        if not 0 <= self.dedup_window_ms <= DEDUP_WINDOW_MS_MAX:
            raise InvalidEntityError(
                f"dedup_window_ms debe estar en [0, 600000]: {self.dedup_window_ms}"
            )

    def _validate_core_settings(self) -> None:
        """Valida los umbrales básicos (compatibles con versiones anteriores)."""
        for name, value in (
            ("max_ocr_per_frame", self.max_ocr_per_frame),
            ("min_plate_width_px", self.min_plate_width_px),
            ("track_finalize_after_ms", self.track_finalize_after_ms),
            ("max_readings_per_track", self.max_readings_per_track),
        ):
            if value < 1:
                raise InvalidEntityError(f"{name} debe ser >= 1: {value}")
        if self.min_sharpness < 0.0:
            raise InvalidEntityError(f"min_sharpness debe ser >= 0: {self.min_sharpness}")
        if not 0.0 <= self.vehicle_crop_margin <= 1.0:
            raise InvalidEntityError(
                f"vehicle_crop_margin fuera de [0, 1]: {self.vehicle_crop_margin}"
            )
        if not self.profile_name.strip():
            raise InvalidEntityError("profile_name no puede estar vacío")

    def _validate_proximity_settings(self) -> None:
        """Valida los parámetros de filtro de proximidad."""
        if not 0.0 <= self.near_min_width_frac <= NEAR_MIN_WIDTH_FRAC_MAX:
            msg = f"near_min_width_frac debe estar en [0, {NEAR_MIN_WIDTH_FRAC_MAX}]: "
            msg += f"{self.near_min_width_frac}"
            raise InvalidEntityError(msg)
        if not 0.0 < self.max_plate_vehicle_ratio <= 1.0:
            raise InvalidEntityError(
                f"max_plate_vehicle_ratio debe estar en (0, 1]: {self.max_plate_vehicle_ratio}"
            )
        try:
            validate_roi(self.roi)
        except ValueError as error:
            raise InvalidEntityError(str(error)) from error


@dataclass(frozen=True, slots=True)
class PipelineDependencies:
    """Puertos que necesita `ProcessVideo` para recorrer y procesar un video."""

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
    """Resultado de una corrida: identificador y estadísticas finales."""

    run_id: int
    stats: RunStats


@dataclass(slots=True)
class _Counters:
    """Contadores mutables acumulados durante una corrida."""

    frames_decoded: int = 0
    frames_processed: int = 0
    tracks_total: int = 0
    sightings_confirmed: int = 0
    sightings_unverified: int = 0
    tracks_without_reading: int = 0
    frame_width: int = 0
    frame_height: int = 0
    proximity: ProximityCounters = field(default_factory=ProximityCounters)
    saved: list[DuplicateCandidate] = field(default_factory=list)


@dataclass(frozen=True, slots=True, eq=False)
class _PlateCandidate:
    """Candidato de lectura de placa: track, caja de placa en el frame y su recorte."""

    track: TrackedVehicle
    pbox: BoundingBox
    detection_confidence: float
    crop: ImageBGR
    sharpness: float


class ProcessVideo:
    """Recorre un video, detecta y sigue vehículos, lee placas y persiste avistamientos."""

    def __init__(self, deps: PipelineDependencies, settings: ProcessingSettings) -> None:
        """Guarda los puertos y los parámetros del perfil de escenario.

        Args:
            deps: puertos usados por el pipeline.
            settings: parámetros del perfil de escenario.
        """
        self._deps = deps
        self._settings = settings

    def execute(
        self, video_path: Path, video_sha256: str, progress: ProgressReporter | None = None
    ) -> RunResult:
        """Procesa el video indicado de principio a fin.

        Args:
            video_path: ruta del video a procesar.
            video_sha256: hash SHA-256 del video, en hexadecimal minúscula.
            progress: reporter opcional del avance; si es `None` no se informa ni se cancela.

        Returns:
            Identificador de la corrida y sus estadísticas finales.

        Raises:
            ProcessingCancelledError: si el reporter pidió cancelar el procesamiento.
            LectorPlacasError: si falla algún paso del pipeline; la corrida queda marcada
                como fallida antes de relanzar el error.
        """
        source = self._deps.source_factory.open(video_path)
        try:
            return self._run(source, video_sha256, progress)
        finally:
            source.close()

    def _run(
        self, source: VideoSource, video_sha256: str, progress: ProgressReporter | None
    ) -> RunResult:
        """Ejecuta la corrida completa sobre una fuente ya abierta."""
        deps = self._deps
        started = deps.clock.now()
        info = source.info()
        run_id = deps.repository.start_run(
            RunStart(video_sha256, self._settings.profile_name, info, started)
        )
        deps.tracker.reset()
        deps.sampler.reset()
        registry = TrackRegistry(self._settings.max_readings_per_track)
        counters = _Counters(frame_width=info.width, frame_height=info.height)
        try:
            self._process_all_frames(source, registry, counters, run_id, progress, info.duration_ms)
            self._finalize(registry.pop_all(), run_id, counters)
            if self._settings.dedup_window_ms != 0:
                pairs = find_duplicates(counters.saved, self._settings.dedup_window_ms)
                deps.repository.mark_duplicates(pairs)
                logger.info("duplicados run_id=%d marcados=%d", run_id, len(pairs))
        except LectorPlacasError as error:
            self._fail_run(run_id, counters, started, info.duration_ms, error)
            raise
        return self._finish_run(run_id, counters, started, info.duration_ms)

    def _process_all_frames(
        self,
        source: VideoSource,
        registry: TrackRegistry,
        counters: _Counters,
        run_id: int,
        progress: ProgressReporter | None,
        duration_ms: int | None,
    ) -> None:
        """Recorre los frames del video, procesando y finalizando tracks inactivos."""
        for frame in source.frames():
            counters.frames_decoded += 1
            if progress is not None and progress.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
            if not self._deps.sampler.should_process(frame.timestamp_ms):
                continue
            counters.frames_processed += 1
            self._process_frame(frame, registry, counters)
            inactive = registry.pop_inactive(
                frame.timestamp_ms, self._settings.track_finalize_after_ms
            )
            self._finalize(inactive, run_id, counters)
            if progress is not None:
                self._report_progress(progress, counters, frame, duration_ms)

    def _report_progress(
        self,
        progress: ProgressReporter,
        counters: _Counters,
        frame: Frame,
        duration_ms: int | None,
    ) -> None:
        """Comunica el avance acumulado tras procesar un frame muestreado."""
        progress.report(
            ProgressUpdate(
                counters.frames_decoded,
                counters.frames_processed,
                frame.timestamp_ms,
                duration_ms,
                counters.sightings_confirmed + counters.sightings_unverified,
            )
        )

    def _process_frame(self, frame: Frame, registry: TrackRegistry, counters: _Counters) -> None:
        """Detecta, sigue y busca placas de los vehículos de un único frame."""
        deps = self._deps
        detections = deps.vehicle_detector.detect(frame.image)
        tracked = deps.tracker.update(detections, frame.image, frame.timestamp_ms)
        registry.observe(tracked, frame.timestamp_ms)
        candidates = self._collect_candidates(tracked, frame, registry, counters)
        if candidates:
            self._record_readings(candidates, frame, registry)

    def _collect_candidates(
        self,
        tracked: list[TrackedVehicle],
        frame: Frame,
        registry: TrackRegistry,
        counters: _Counters,
    ) -> list[_PlateCandidate]:
        """Elige, hasta el máximo por frame, los tracks que aún necesitan lectura con filtros."""
        # Paso 1: Elegir tracks que necesiten lectura
        eligible = [t for t in tracked if registry.needs_reading(t.track_id)]

        # Paso 2-3: Filtrar por ROI y tamaño de vehículo
        min_width = effective_min_width(
            frame.width,
            frame.height,
            self._settings.min_plate_width_px,
            self._settings.near_min_width_frac,
        )
        min_vehicle_width = min_width / self._settings.max_plate_vehicle_ratio

        roi_filtered = []
        for track in eligible:
            if not center_in_roi(track.box, self._settings.roi, frame.width, frame.height):
                counters.proximity.outside_roi += 1
                continue
            if track.box.width < min_vehicle_width:
                counters.proximity.small_vehicle += 1
                continue
            roi_filtered.append(track)

        # Paso 4: Ordenar y tomar top
        ordered = sorted(roi_filtered, key=lambda t: (registry.is_full(t.track_id), -t.box.area))

        # Paso 5-6: Por cada track elegido, aplicar filtros adicionales
        candidates: list[_PlateCandidate] = []
        for tracked_vehicle in ordered[: self._settings.max_ocr_per_frame]:
            candidate = self._plate_candidate(tracked_vehicle, frame, min_width, counters)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _plate_candidate(
        self,
        tracked_vehicle: TrackedVehicle,
        frame: Frame,
        min_width: int,
        counters: _Counters,
    ) -> _PlateCandidate | None:
        """Recorta el vehículo, detecta su placa y valida tamaño, borde y nitidez."""
        deps = self._deps
        vbox = _expand_vehicle_box(tracked_vehicle.box, self._settings.vehicle_crop_margin, frame)
        if vbox is None:
            counters.proximity.small_vehicle += 1
        else:
            vehicle_crop = crop_image(frame.image, vbox)
            plates = deps.plate_detector.detect(vehicle_crop)
            found = _best_plate_box(plates, vbox, frame)
            if found is not None:
                best_confidence, pbox = found
                if self._plate_is_near(pbox, frame, min_width, counters):
                    plate_crop = crop_image(frame.image, pbox)
                    sharp = deps.quality.sharpness(plate_crop)
                    if sharp >= self._settings.min_sharpness:
                        return _PlateCandidate(
                            tracked_vehicle, pbox, best_confidence, plate_crop, sharp
                        )
                    counters.proximity.blurry += 1
            else:
                counters.proximity.no_plate += 1
        return None

    def _plate_is_near(
        self, pbox: BoundingBox, frame: Frame, min_width: int, counters: _Counters
    ) -> bool:
        """Valida que la placa detectada esté cerca: no toque borde ni sea muy estrecha."""
        if touches_frame_edge(pbox, frame.width, frame.height):
            counters.proximity.plate_at_edge += 1
            return False
        if pbox.width < min_width:
            counters.proximity.narrow_plate += 1
            return False
        return True

    def _record_readings(
        self, candidates: list[_PlateCandidate], frame: Frame, registry: TrackRegistry
    ) -> None:
        """Lee en lote los recortes de placa y registra las lecturas no vacías."""
        deps = self._deps
        results = deps.reader.read([candidate.crop for candidate in candidates])
        for candidate, result in zip(candidates, results, strict=True):
            if result.text == "":
                continue
            reading = PlateReading(
                candidate.track.track_id,
                frame.index,
                frame.timestamp_ms,
                result.text,
                result.char_confidences,
                candidate.pbox,
                candidate.detection_confidence,
                candidate.sharpness,
            )
            registry.add_reading(reading, candidate.crop)
            self._check_early_stop(registry, reading.track_id)

    def _check_early_stop(self, registry: TrackRegistry, track_id: int) -> None:
        """Marca el track como resuelto si está lleno y sus lecturas actuales se confirmarían."""
        if not self._settings.early_stop or not registry.is_full(track_id):
            return
        plate = self._deps.consolidator.consolidate(
            registry.readings(track_id), registry.vehicle_type(track_id)
        )
        if plate.status is ReviewStatus.CONFIRMED:
            registry.mark_resolved(track_id)

    def _finalize(self, tracks: list[FinalizedTrack], run_id: int, counters: _Counters) -> None:
        """Consolida y persiste los tracks finalizados; descarta los que no tuvieron lecturas."""
        for track in tracks:
            counters.tracks_total += 1
            if not track.readings:
                counters.tracks_without_reading += 1
                continue
            self._save_track(track, run_id, counters)

    def _save_track(self, track: FinalizedTrack, run_id: int, counters: _Counters) -> None:
        """Consolida las lecturas de un track, lo persiste y registra el resultado."""
        deps = self._deps
        plate = deps.consolidator.consolidate(track.readings, track.vehicle_type)
        crop_ref = deps.crop_store.save(track.best_crop) if track.best_crop is not None else None
        quality: CropQuality | None = None
        if track.best_crop is not None:
            quality = CropQuality(
                track.best_crop.shape[1],
                track.best_crop.shape[0],
                deps.quality.sharpness(track.best_crop),
                rms_contrast(track.best_crop),
            )
        plate = self._apply_legibility(plate, quality, track, counters)
        sighting = Sighting(
            run_id,
            track.track_id,
            track.first_seen_ms,
            track.last_seen_ms,
            track.vehicle_type,
            plate,
            crop_ref,
            deps.clock.now(),
            quality,
        )
        sighting_id = deps.repository.save_sighting(sighting)
        counters.saved.append(
            DuplicateCandidate(
                sighting_id,
                plate.text,
                plate.status,
                plate.confidence,
                track.first_seen_ms,
                track.last_seen_ms,
            )
        )
        if plate.status is ReviewStatus.CONFIRMED:
            counters.sightings_confirmed += 1
        else:
            counters.sightings_unverified += 1
        logger.info(
            "avistamiento run_id=%d track_id=%d estado=%s placa=%s",
            run_id,
            track.track_id,
            plate.status,
            mask_plate(plate.text),
        )

    def _apply_legibility(
        self,
        plate: ConsolidatedPlate,
        quality: CropQuality | None,
        track: FinalizedTrack,
        counters: _Counters,
    ) -> ConsolidatedPlate:
        """Marca el consolidado como sin confirmar si el filtro de legibilidad lo rechaza."""
        model = self._settings.legibility
        if model is None or quality is None:
            return plate
        features = feature_vector(
            plate, quality, counters.frame_width, counters.frame_height, track.vehicle_type
        )
        reason = legibility_reason(model, features)
        if reason is None:
            return plate
        return dataclasses.replace(
            plate, status=ReviewStatus.UNVERIFIED, reasons=(*plate.reasons, reason)
        )

    def _fail_run(
        self,
        run_id: int,
        counters: _Counters,
        started: datetime,
        video_duration_ms: int | None,
        error: LectorPlacasError,
    ) -> None:
        """Cierra la corrida como fallida y registra el error, descartando tracks pendientes."""
        deps = self._deps
        finished = deps.clock.now()
        stats = self._stats(counters, started, finished, video_duration_ms)
        deps.repository.finish_run(run_id, stats, finished, False)
        logger.error("corrida fallida run_id=%d error=%s", run_id, type(error).__name__)

    def _finish_run(
        self, run_id: int, counters: _Counters, started: datetime, video_duration_ms: int | None
    ) -> RunResult:
        """Cierra la corrida como exitosa y registra sus estadísticas finales."""
        deps = self._deps
        finished = deps.clock.now()
        stats = self._stats(counters, started, finished, video_duration_ms)
        deps.repository.finish_run(run_id, stats, finished, True)
        p = counters.proximity
        logger.info(
            "cercania run_id=%d fuera_roi=%d vehiculo_pequeno=%d sin_placa=%d"
            " placa_en_borde=%d placa_estrecha=%d borrosa=%d",
            run_id,
            p.outside_roi,
            p.small_vehicle,
            p.no_plate,
            p.plate_at_edge,
            p.narrow_plate,
            p.blurry,
        )
        logger.info(
            "corrida terminada run_id=%d frames_procesados=%d confirmados=%d"
            " sin_confirmar=%d sin_lectura=%d duracion_ms=%d",
            run_id,
            stats.frames_processed,
            stats.sightings_confirmed,
            stats.sightings_unverified,
            stats.tracks_without_reading,
            stats.processing_ms,
        )
        return RunResult(run_id, stats)

    def _stats(
        self,
        counters: _Counters,
        started: datetime,
        finished: datetime,
        video_duration_ms: int | None,
    ) -> RunStats:
        """Construye `RunStats` a partir de los contadores y la duración transcurrida."""
        processing_ms = int((finished - started).total_seconds() * 1000)
        return RunStats(
            counters.frames_decoded,
            counters.frames_processed,
            counters.tracks_total,
            counters.sightings_confirmed,
            counters.sightings_unverified,
            counters.tracks_without_reading,
            processing_ms,
            video_duration_ms,
        )


def _expand_vehicle_box(box: BoundingBox, margin: float, frame: Frame) -> BoundingBox | None:
    """Agranda la caja de vehículo el margen configurado y descarta recortes demasiado chicos."""
    vbox = box.expand(margin, frame.width, frame.height)
    if vbox is None or vbox.width < MIN_VEHICLE_CROP_PX or vbox.height < MIN_VEHICLE_CROP_PX:
        return None
    return vbox


def _best_plate_box(
    plates: list[PlateDetection], vbox: BoundingBox, frame: Frame
) -> tuple[float, BoundingBox] | None:
    """Elige la placa de mayor confianza y la traslada al frame."""
    if not plates:
        return None
    best = max(plates, key=lambda plate: plate.confidence)
    pbox = best.box.translate(math.floor(vbox.x1), math.floor(vbox.y1)).clip(
        frame.width, frame.height
    )
    if pbox is None:
        return None
    return best.confidence, pbox
