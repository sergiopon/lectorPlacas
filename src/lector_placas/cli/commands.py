"""Manejadores de los subcomandos de la CLI `lector`.

Cada manejador construye sus adaptadores reales llamando siempre a `composition.<función>`
(nunca instanciando adaptadores directamente), para que los tests puedan sustituir la
composición sin tocar este módulo (ARQUITECTURA.md §2 regla 4).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from lector_placas.adapters.review.opencv_review_ui import OpenCvReviewUI
from lector_placas.application.export_sightings import ExportSightings
from lector_placas.application.ports import Clock, CropStore, ExportStore, PlateRepository
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.application.review_sightings import ReviewSightings
from lector_placas.cli import composition
from lector_placas.domain.entities import ReviewStatus
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.input_validation import sha256_file, validate_video_path
from lector_placas.infrastructure.model_fetcher import default_opener, fetch_models
from lector_placas.infrastructure.model_registry import PENDING_EXPORT, load_manifest

if TYPE_CHECKING:
    from lector_placas.infrastructure.config import AppConfig

_DbAction = Callable[[PlateRepository, CropStore, ExportStore, Clock, PurgeResult], int]


def cmd_key_init(args: argparse.Namespace, config: AppConfig) -> int:
    """Asegura la clave maestra en el llavero del sistema, creándola si no existe."""
    composition.build_key_provider(True).master_key()
    sys.stdout.write("clave maestra disponible en el keyring\n")
    return 0


def cmd_models_fetch(args: argparse.Namespace, config: AppConfig) -> int:
    """Descarga y verifica los modelos del manifiesto que tengan URL."""
    manifest = config.under_root(config.paths.model_manifest)
    models_dir = config.under_root(config.paths.models_dir)
    ids = fetch_models(manifest, models_dir, default_opener)
    sys.stdout.write(f"descargados: {', '.join(ids) or 'ninguno'}\n")
    return 0


def cmd_models_verify(args: argparse.Namespace, config: AppConfig) -> int:
    """Verifica cada modelo del manifiesto contra su SHA-256 esperado."""
    manifest = load_manifest(config.under_root(config.paths.model_manifest))
    registry = composition.build_registry(config)
    for entry in manifest.models:
        if entry.sha256 == PENDING_EXPORT:
            sys.stdout.write(f"{entry.model_id}: pendiente de exportar\n")
            continue
        registry.verified_path(entry.model_id)
        sys.stdout.write(f"{entry.model_id}: ok\n")
    return 0


def cmd_process(args: argparse.Namespace, config: AppConfig) -> int:
    """Valida el video y ejecuta el pipeline completo sobre él."""
    name, _ = config.profile(args.profile)
    allowed_dirs = [config.under_root(d) for d in config.input.allowed_dirs]
    video = validate_video_path(
        args.video,
        allowed_dirs,
        frozenset(config.input.allowed_extensions),
        config.input.max_file_size_mb * 1024 * 1024,
    )
    sha = sha256_file(video)

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del export_store, purge
        use_case = composition.build_process_video(config, name, repository, crop_store, clock)
        result = use_case.execute(video, sha)
        s = result.stats
        vel = f"{s.speed_factor:.2f}x" if s.speed_factor is not None else "n/d"
        sys.stdout.write(
            f"run_id={result.run_id} frames={s.frames_processed}/{s.frames_decoded} "
            f"confirmadas={s.sightings_confirmed} sin_verificar={s.sightings_unverified} "
            f"sin_lectura={s.tracks_without_reading} velocidad={vel}\n"
        )
        return 0

    return _run_with_repository(config, action)


def cmd_review(args: argparse.Namespace, config: AppConfig) -> int:
    """Revisa hasta `args.limit` avistamientos sin verificar por terminal."""

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del export_store, purge
        use_case = ReviewSightings(repository, crop_store, OpenCvReviewUI(), clock)
        summary = use_case.execute(args.limit)
        sys.stdout.write(
            f"confirmados={summary.confirmed} corregidos={summary.corrected} "
            f"rechazados={summary.rejected} omitidos={summary.skipped}\n"
        )
        return 0

    return _run_with_repository(config, action)


def cmd_export(args: argparse.Namespace, config: AppConfig) -> int:
    """Exporta los avistamientos con el estado indicado (o todos) a un CSV."""

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del crop_store, purge
        status = ReviewStatus(args.status) if args.status else None
        path = ExportSightings(repository, export_store, clock).execute(status)
        sys.stdout.write(f"exportado: {path.name}\n")
        return 0

    return _run_with_repository(config, action)


def cmd_purge(args: argparse.Namespace, config: AppConfig) -> int:
    """Ejecuta la purga por retención, que ya se aplica al abrir la base de datos."""

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del repository, crop_store, export_store, clock
        sys.stdout.write(
            f"recortes={purge.crops_deleted} avistamientos={purge.sightings_deleted} "
            f"corridas={purge.runs_deleted} placas={purge.plates_deleted} "
            f"exportaciones={purge.exports_deleted}\n"
        )
        return 0

    return _run_with_repository(config, action)


def _run_with_repository(config: AppConfig, action: _DbAction) -> int:
    """Abre el repositorio, purga los datos vencidos y ejecuta `action` (SEG-03).

    Args:
        config: configuración de la aplicación.
        action: función que recibe los puertos abiertos y el resultado de la purga.

    Returns:
        El código de salida devuelto por `action`.
    """
    keys = composition.build_key_provider(False)
    clock = SystemClock()
    repository = composition.build_repository(config, keys)
    try:
        crop_store = composition.build_crop_store(config, keys)
        export_store = composition.build_export_store(config)
        purge_use_case = composition.build_purge(
            config, repository, crop_store, export_store, clock
        )
        purge = purge_use_case.execute()
        return action(repository, crop_store, export_store, clock, purge)
    finally:
        repository.close()
