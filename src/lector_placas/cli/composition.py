"""Composition root: construye los adaptadores reales a partir de la configuración.

Único módulo del proyecto con inyección manual de dependencias concretas
(ARQUITECTURA.md §2 regla 4). `commands.py` llama siempre a través de `composition.<función>`
para que los tests de integración puedan sustituir cualquiera de estas funciones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from lector_placas.adapters.export.csv_export_store import CsvExportStore
from lector_placas.adapters.export.training_export_store import FilesystemTrainingExportStore
from lector_placas.adapters.imaging.quality import LaplacianQualityScorer
from lector_placas.adapters.inference.onnx_session import (
    create_session,
    ensure_cuda_libraries,
    providers_for,
)
from lector_placas.adapters.inference.plate_detector_oim import create_oim_plate_detector
from lector_placas.adapters.inference.plate_detector_yolo import YoloPlateDetector
from lector_placas.adapters.inference.plate_reader_fpo import create_fast_plate_ocr_reader
from lector_placas.adapters.inference.vehicle_detector_yolo import YoloVehicleDetector
from lector_placas.adapters.inference.yolo_end2end import YoloEnd2EndOnnxModel
from lector_placas.adapters.persistence.sqlcipher_repository import SqlCipherPlateRepository
from lector_placas.adapters.security.keyring_key_provider import KeyringKeyProvider
from lector_placas.adapters.storage.encrypted_crop_store import EncryptedFileCropStore
from lector_placas.adapters.tracking.botsort_tracker import BotSortTracker, TrackerSettings
from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory
from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.ports import (
    Clock,
    CropStore,
    ExportStore,
    KeyProvider,
    ModelRegistry,
    PlateDetector,
    PlateReader,
    PlateRepository,
    Tracker,
    VehicleDetector,
)
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.consolidation import VotingPlateConsolidator
from lector_placas.infrastructure.config import AppConfig, ProfileConfig
from lector_placas.infrastructure.model_registry import ManifestModelRegistry
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

DB_FILENAME: Final[Path] = Path("lector.db")
CROPS_DIRNAME: Final[Path] = Path("crops")
EXPORTS_DIRNAME: Final[Path] = Path("exports")
TRAINING_EXPORT_DIR: Final[Path] = Path("training/ocr/datasets/own")


def data_dir(config: AppConfig) -> Path:
    """Devuelve el directorio privado de datos de la aplicación, creándolo si hace falta."""
    return ensure_private_dir(config.under_root(config.paths.data_dir))


def build_key_provider(create_if_missing: bool) -> KeyProvider:
    """Construye el proveedor de la clave maestra respaldado por el llavero del sistema."""
    return KeyringKeyProvider(create_if_missing)


def build_repository(config: AppConfig, keys: KeyProvider) -> SqlCipherPlateRepository:
    """Construye el repositorio SQLCipher dentro del directorio privado de datos."""
    return SqlCipherPlateRepository(resolve_within(data_dir(config), DB_FILENAME), keys)


def build_crop_store(config: AppConfig, keys: KeyProvider) -> EncryptedFileCropStore:
    """Construye el almacén de recortes cifrados dentro del directorio privado de datos."""
    return EncryptedFileCropStore(resolve_within(data_dir(config), CROPS_DIRNAME), keys)


def build_export_store(config: AppConfig) -> CsvExportStore:
    """Construye el almacén de exportaciones dentro del directorio privado de datos."""
    return CsvExportStore(resolve_within(data_dir(config), EXPORTS_DIRNAME))


def build_training_store(config: AppConfig) -> FilesystemTrainingExportStore:
    """Construye el almacén de recortes revisados para reentrenar el OCR (SEG-07)."""
    return FilesystemTrainingExportStore(resolve_within(config.root_dir, TRAINING_EXPORT_DIR))


def build_registry(config: AppConfig) -> ManifestModelRegistry:
    """Construye el registro de modelos a partir del manifiesto configurado."""
    return ManifestModelRegistry(
        config.under_root(config.paths.model_manifest),
        config.under_root(config.paths.models_dir),
    )


def build_purge(
    config: AppConfig,
    repository: PlateRepository,
    crop_store: CropStore,
    export_store: ExportStore,
    clock: Clock,
) -> PurgeExpiredData:
    """Construye el caso de uso de purga con la política de retención configurada."""
    retention = config.retention
    policy = RetentionPolicy(retention.crops_days, retention.records_days, retention.training_days)
    return PurgeExpiredData(
        repository,
        crop_store,
        export_store,
        clock,
        policy,
        training_store=build_training_store(config),
    )


def build_vehicle_detector(config: AppConfig, registry: ModelRegistry) -> VehicleDetector:
    """Construye el detector de vehículos YOLO a partir del modelo configurado."""
    ep = config.inference.execution_provider
    vd = config.models.vehicle_detector
    session = create_session(registry.verified_path(vd.model_id), ep)
    model = YoloEnd2EndOnnxModel(session, vd.input_size)
    return YoloVehicleDetector(model, vd.score_threshold)


def build_plate_detector(config: AppConfig, registry: ModelRegistry) -> PlateDetector:
    """Construye el detector de placas según el backend configurado."""
    ep = config.inference.execution_provider
    pd = config.models.plate_detector
    model_path = registry.verified_path(pd.model_id)
    if pd.backend == "open_image_models":
        ensure_cuda_libraries(ep)
        return create_oim_plate_detector(model_path, pd.score_threshold, providers_for(ep))
    session = create_session(model_path, ep)
    model = YoloEnd2EndOnnxModel(session, pd.input_size)
    return YoloPlateDetector(model, pd.score_threshold)


def build_reader(config: AppConfig, registry: ModelRegistry) -> PlateReader:
    """Construye el lector OCR de placas a partir del modelo y la configuración configurados."""
    ep = config.inference.execution_provider
    ocr = config.models.ocr
    ensure_cuda_libraries(ep)
    return create_fast_plate_ocr_reader(
        registry.verified_path(ocr.model_id),
        registry.verified_path(ocr.config_id),
        providers_for(ep),
    )


def build_tracker(config: AppConfig, profile: ProfileConfig) -> Tracker:
    """Construye el tracker BoT-SORT con los parámetros configurados y el fps del perfil."""
    t = config.tracker
    settings = TrackerSettings(
        t.lost_track_buffer,
        profile.target_fps,
        t.track_activation_threshold,
        t.minimum_consecutive_frames,
        t.minimum_iou_threshold_first_assoc,
        t.minimum_iou_threshold_second_assoc,
        t.minimum_iou_threshold_unconfirmed_assoc,
        t.high_conf_det_threshold,
        t.cmc_method,
        t.cmc_downscale,
    )
    return BotSortTracker(settings)


def build_process_video(
    config: AppConfig,
    profile_name: str,
    repository: PlateRepository,
    crop_store: CropStore,
    clock: Clock,
) -> ProcessVideo:
    """Construye el caso de uso `ProcessVideo` con todos sus adaptadores reales."""
    name, profile = config.profile(profile_name)
    registry = build_registry(config)
    deps = PipelineDependencies(
        PyAVVideoSourceFactory(),
        TimeBasedFrameSampler(profile.target_fps),
        build_vehicle_detector(config, registry),
        build_plate_detector(config, registry),
        build_tracker(config, profile),
        build_reader(config, registry),
        LaplacianQualityScorer(),
        VotingPlateConsolidator(
            config.plate_catalog(), config.consolidation_policy(profile), config.confusion_map()
        ),
        repository,
        crop_store,
        clock,
    )
    settings = ProcessingSettings(
        name,
        profile.max_ocr_per_frame,
        profile.min_plate_width_px,
        profile.min_sharpness,
        profile.vehicle_crop_margin,
        profile.track_finalize_after_ms,
        profile.max_readings_per_track,
    )
    return ProcessVideo(deps, settings)
