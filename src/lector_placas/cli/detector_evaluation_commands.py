"""Subcomando `evaluate-detector` de la CLI `lector`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from lector_placas.application.ports import PlateDetector
from lector_placas.cli import composition, evaluation_commands
from lector_placas.datasets.yolo_split import LabeledImage, iter_split
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.detection_metrics import (
    IOU_THRESHOLD,
    DetectionCounts,
    DetectionMetrics,
    match_image,
    summarize,
)
from lector_placas.evaluation.report import write_report
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.paths import resolve_within

if TYPE_CHECKING:
    from lector_placas.infrastructure.config import AppConfig

DEFAULT_DATASET: Final[Path] = Path("training/detector/datasets/merged")
MIN_SIDE_PX: Final[int] = 16


def register_detector_evaluation(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Registra `evaluate-detector` en el parser de la CLI.

    Args:
        subparsers: acción de subparsers de `main.build_parser`.
    """
    parser = subparsers.add_parser("evaluate-detector")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--iou", type=float, default=IOU_THRESHOLD)
    parser.set_defaults(handler=cmd_evaluate_detector, network=False)


def cmd_evaluate_detector(args: argparse.Namespace, config: AppConfig) -> int:
    """Evalúa el detector de placas sobre un split del dataset y guarda el reporte."""
    if not 0.0 < args.iou <= 1.0:
        raise EvaluationError(f"umbral IoU fuera de (0, 1]: {args.iou}")
    dataset = resolve_within(config.root_dir, args.dataset)
    detector = composition.build_plate_detector(config, composition.build_registry(config))
    counts, skipped = _evaluate(dataset, args.split, args.iou, detector)
    metrics = summarize(counts)
    payload = _payload(dataset, args.split, args.iou, metrics, skipped, config)
    report = write_report(evaluation_commands._reports_dir(config), payload, SystemClock().now())
    _write_summary(metrics, skipped, report.name)
    return 0


def _evaluate(
    dataset: Path, split: str, threshold: float, detector: PlateDetector
) -> tuple[list[DetectionCounts], int]:
    """Empareja las predicciones de cada imagen con sus placas anotadas.

    Returns:
        Los conteos de las imágenes evaluadas y cuántas se omitieron por ser menores
        que `MIN_SIDE_PX` píxeles de lado.
    """
    counts: list[DetectionCounts] = []
    skipped = 0
    for item in iter_split(dataset, split):
        if _min_side(item) < MIN_SIDE_PX:
            skipped += 1
            continue
        counts.append(match_image(detector.detect(item.image), item.boxes, threshold))
    return counts, skipped


def _min_side(item: LabeledImage) -> int:
    """Menor lado de la imagen en píxeles."""
    height, width = int(item.image.shape[0]), int(item.image.shape[1])
    return min(height, width)


def _payload(
    dataset: Path,
    split: str,
    threshold: float,
    metrics: DetectionMetrics,
    skipped: int,
    config: AppConfig,
) -> dict[str, object]:
    """Construye el contenido del reporte, sin rutas ni nombres de imagen."""
    counts = metrics.counts
    return {
        "kind": "detector",
        "dataset": dataset.name,
        "split": split,
        "iou_threshold": threshold,
        "images": metrics.images,
        "skipped": skipped,
        "true_positives": counts.true_positives,
        "false_positives": counts.false_positives,
        "false_negatives": counts.false_negatives,
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1": metrics.f1,
        "backend": config.models.plate_detector.backend,
        "model_id": config.models.plate_detector.model_id,
    }


def _write_summary(metrics: DetectionMetrics, skipped: int, report_name: str) -> None:
    """Escribe en stdout las métricas y el nombre del reporte, sin placas ni rutas."""
    counts = metrics.counts
    sys.stdout.write(
        f"images={metrics.images} skipped={skipped} tp={counts.true_positives} "
        f"fp={counts.false_positives} fn={counts.false_negatives} "
        f"precision={evaluation_commands._format_metric(metrics.precision)} "
        f"recall={evaluation_commands._format_metric(metrics.recall)} "
        f"f1={evaluation_commands._format_metric(metrics.f1)}\n"
    )
    sys.stdout.write(f"reporte={report_name}\n")
