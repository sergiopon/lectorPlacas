"""Subcomandos `evaluate` y `evaluate-ocr` de la CLI `lector` (spec 029)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import cv2

from lector_placas.application.ports import (
    Clock,
    CropStore,
    ExportStore,
    ImageBGR,
    PlateReader,
    PlateRepository,
    RunStats,
)
from lector_placas.application.process_video import ProcessVideo, RunResult
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import commands, composition
from lector_placas.cli.commands import _run_with_repository
from lector_placas.domain.entities import SightingRecord
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.cer import character_error_rate, exact_match_rate
from lector_placas.evaluation.ground_truth import GroundTruth, load_ground_truth
from lector_placas.evaluation.metrics import PlateMetrics, compute_metrics
from lector_placas.evaluation.ocr_dataset import read_ocr_annotations
from lector_placas.evaluation.report import write_report
from lector_placas.evaluation.vram_monitor import VramMonitor
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.input_validation import sha256_file
from lector_placas.infrastructure.paths import resolve_within

if TYPE_CHECKING:
    from lector_placas.infrastructure.config import AppConfig

BATCH_SIZE: Final[int] = 64
PAGE_SIZE: Final[int] = 500
REPORTS_DIRNAME: Final[Path] = Path("eval/reports")


def register_evaluation_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Registra `evaluate` y `evaluate-ocr` en el parser de la CLI.

    Args:
        subparsers: acción de subparsers de `main.build_parser`.
    """
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--video", type=Path, required=True)
    evaluate_parser.add_argument("--ground-truth", type=Path, required=True)
    evaluate_parser.add_argument("--profile", default=None)
    evaluate_parser.add_argument("--skip-vram", action="store_true")
    evaluate_parser.set_defaults(handler=cmd_evaluate, network=False)

    ocr_parser = subparsers.add_parser("evaluate-ocr")
    ocr_parser.add_argument("--crops", type=Path, required=True)
    ocr_parser.set_defaults(handler=cmd_evaluate_ocr, network=False)


def cmd_evaluate(args: argparse.Namespace, config: AppConfig) -> int:
    """Procesa un video y calcula M-01..M-03, M-05 y M-06 contra su ground truth."""
    name, _ = config.profile(args.profile)
    video = commands.validated_video(config, args.video)
    digest = sha256_file(video)
    truth = load_ground_truth(resolve_within(config.root_dir, args.ground_truth))
    if truth.video_sha256 != digest:
        raise EvaluationError("el ground truth no corresponde al video")
    skip_vram = bool(args.skip_vram)

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del export_store, purge
        use_case = composition.build_process_video(config, name, repository, crop_store, clock)
        result, peak = _execute_run(use_case, video, digest, skip_vram)
        metrics = compute_metrics(_records_for_run(repository, result.run_id), truth)
        payload = _video_payload(name, truth, result.run_id, metrics, result.stats, peak)
        report = write_report(_reports_dir(config), payload, clock.now())
        _write_video_summary(metrics, result.stats.speed_factor, peak, report.name)
        return 0

    return _run_with_repository(config, action)


def cmd_evaluate_ocr(args: argparse.Namespace, config: AppConfig) -> int:
    """Ejecuta el OCR configurado sobre los recortes anotados y calcula M-04."""
    sources = read_ocr_annotations(resolve_within(config.root_dir, args.crops))
    reader = composition.build_reader(config, composition.build_registry(config))
    predictions = _predict_texts(reader, sources)
    pairs = [
        (prediction, truth) for prediction, (_, truth) in zip(predictions, sources, strict=True)
    ]
    rate = character_error_rate(pairs)
    exact = exact_match_rate(pairs)
    payload: dict[str, object] = {
        "kind": "ocr",
        "samples": len(pairs),
        "cer": rate,
        "exact_match_rate": exact,
        "model_id": config.models.ocr.model_id,
    }
    report = write_report(_reports_dir(config), payload, SystemClock().now())
    sys.stdout.write(
        f"samples={len(pairs)} cer={_format_metric(rate)} "
        f"exact_match_rate={_format_metric(exact)}\n"
    )
    sys.stdout.write(f"reporte={report.name}\n")
    return 0


def _execute_run(
    use_case: ProcessVideo, video: Path, digest: str, skip_vram: bool
) -> tuple[RunResult, int | None]:
    """Ejecuta el pipeline midiendo la VRAM pico salvo que se omita el monitoreo."""
    if skip_vram:
        return use_case.execute(video, digest), None
    with VramMonitor() as monitor:
        result = use_case.execute(video, digest)
    return result, monitor.peak_mib


def _records_for_run(repository: PlateRepository, run_id: int) -> list[SightingRecord]:
    """Recupera, paginando, los avistamientos de una corrida."""
    records: list[SightingRecord] = []
    offset = 0
    while True:
        page = repository.list_sightings(None, PAGE_SIZE, offset)
        records.extend(record for record in page if record.run_id == run_id)
        if len(page) < PAGE_SIZE:
            return records
        offset += PAGE_SIZE


def _video_payload(
    name: str,
    truth: GroundTruth,
    run_id: int,
    metrics: PlateMetrics,
    stats: RunStats,
    peak_mib: int | None,
) -> dict[str, object]:
    """Construye el contenido del reporte de una evaluación de video."""
    return {
        "kind": "video",
        "subset": truth.subset,
        "camera": truth.camera,
        "profile": name,
        "run_id": run_id,
        "gt_legible": metrics.gt_legible,
        "confirmed_total": metrics.confirmed_total,
        "confirmed_matched": metrics.confirmed_matched,
        "any_matched": metrics.any_matched,
        "corrected_total": metrics.corrected_total,
        "precision_confirmed": metrics.precision_confirmed,
        "recall_any": metrics.recall_any,
        "recall_confirmed": metrics.recall_confirmed,
        "speed_factor": stats.speed_factor,
        "vram_peak_mib": peak_mib,
    }


def _predict_texts(reader: PlateReader, sources: Sequence[tuple[Path, str]]) -> list[str]:
    """Lee los recortes en lotes y devuelve el texto predicho de cada uno."""
    predictions: list[str] = []
    for start in range(0, len(sources), BATCH_SIZE):
        chunk = sources[start : start + BATCH_SIZE]
        images = [_load_image(path) for path, _ in chunk]
        predictions.extend(result.text for result in reader.read(images))
    return predictions


def _load_image(path: Path) -> ImageBGR:
    """Carga una imagen BGR; falla si `cv2` no puede decodificarla."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise EvaluationError(f"imagen ilegible: {path.name}")
    return cast(ImageBGR, image)


def _reports_dir(config: AppConfig) -> Path:
    """Directorio privado de reportes de evaluación."""
    return resolve_within(composition.data_dir(config), REPORTS_DIRNAME)


def _format_metric(value: float | None) -> str:
    """Formatea una métrica con cuatro decimales, o `n/d` si no tiene denominador."""
    return "n/d" if value is None else f"{value:.4f}"


def _write_video_summary(
    metrics: PlateMetrics, speed_factor: float | None, peak_mib: int | None, report_name: str
) -> None:
    """Escribe en stdout las métricas de video y el nombre del reporte, sin placas."""
    peak_text = "n/d" if peak_mib is None else str(peak_mib)
    sys.stdout.write(
        f"gt_legible={metrics.gt_legible} confirmed_total={metrics.confirmed_total} "
        f"confirmed_matched={metrics.confirmed_matched} any_matched={metrics.any_matched} "
        f"corrected_total={metrics.corrected_total} "
        f"precision_confirmed={_format_metric(metrics.precision_confirmed)} "
        f"recall_any={_format_metric(metrics.recall_any)} "
        f"recall_confirmed={_format_metric(metrics.recall_confirmed)} "
        f"speed_factor={_format_metric(speed_factor)} vram_peak_mib={peak_text}\n"
    )
    sys.stdout.write(f"reporte={report_name}\n")
