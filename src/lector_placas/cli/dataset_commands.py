"""Subcomandos `lector dataset`: preparan offline los datos de entrenamiento locales."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from lector_placas.application.export_reviewed import ExportReviewedCrops
from lector_placas.cli import commands, composition
from lector_placas.datasets.chars_to_ocr import chars_to_ocr
from lector_placas.datasets.merge_detection import merge_detection
from lector_placas.infrastructure.paths import resolve_within

if TYPE_CHECKING:
    from lector_placas.application.ports import Clock, CropStore, ExportStore, PlateRepository
    from lector_placas.application.purge_expired import PurgeResult
    from lector_placas.infrastructure.config import AppConfig

DETECTOR_ROOT: Final[Path] = Path("training/detector")
OCR_DATASETS_ROOT: Final[Path] = Path("training/ocr/datasets")
RAW_DIR: Final[str] = "raw"


def register_dataset_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Agrega el subcomando `dataset` con sus operaciones.

    Args:
        subparsers: subparsers del parser principal de `lector`.
    """
    dataset_parser = subparsers.add_parser("dataset")
    dataset_sub = dataset_parser.add_subparsers(dest="dataset_command", required=True)
    merge_parser = dataset_sub.add_parser("merge-detection")
    merge_parser.add_argument("--sources", type=Path, required=True)
    merge_parser.add_argument("--output", required=True)
    merge_parser.set_defaults(handler=cmd_merge_detection, network=False)
    chars_parser = dataset_sub.add_parser("chars-to-ocr")
    chars_parser.add_argument("--source", type=Path, required=True)
    chars_parser.add_argument("--output", required=True)
    chars_parser.set_defaults(handler=cmd_chars_to_ocr, network=False)
    reviewed_parser = dataset_sub.add_parser("export-reviewed")
    reviewed_parser.set_defaults(handler=cmd_export_reviewed, network=False, key="load")


def cmd_merge_detection(args: argparse.Namespace, config: AppConfig) -> int:
    """Une las fuentes de detección declaradas en un dataset YOLO de una clase.

    Args:
        args: argumentos con `sources` (YAML de fuentes) y `output` (nombre de salida).
        config: configuración de la aplicación, usada como raíz de las rutas.

    Returns:
        El código de salida 0.
    """
    datasets_root = config.root_dir / DETECTOR_ROOT / "datasets"
    summary = merge_detection(
        resolve_within(config.root_dir / DETECTOR_ROOT, args.sources),
        datasets_root / RAW_DIR,
        resolve_within(datasets_root, Path(args.output)),
    )
    sys.stdout.write(
        f"train={summary.train_images} val={summary.val_images} "
        f"duplicados={summary.dropped_duplicates} cajas={summary.boxes}\n"
    )
    return 0


def cmd_chars_to_ocr(args: argparse.Namespace, config: AppConfig) -> int:
    """Convierte un dataset anotado por carácter en recortes de placa para el OCR.

    Args:
        args: argumentos con `source` (directorio del dataset) y `output` (nombre de salida).
        config: configuración de la aplicación, usada como raíz de las rutas y del catálogo.

    Returns:
        El código de salida 0.
    """
    datasets_root = config.root_dir / OCR_DATASETS_ROOT
    summary = chars_to_ocr(
        resolve_within(datasets_root / RAW_DIR, args.source),
        resolve_within(datasets_root, Path(args.output)),
        config.plate_catalog(),
    )
    sys.stdout.write(
        f"train={summary.train_crops} val={summary.val_crops} "
        f"omitidos={summary.skipped} duplicados={summary.dropped_duplicates}\n"
    )
    return 0


def cmd_export_reviewed(args: argparse.Namespace, config: AppConfig) -> int:
    """Exporta los recortes de los avistamientos revisados para reentrenar el OCR.

    Args:
        args: argumentos del subcomando (ninguno propio).
        config: configuración de la aplicación.

    Returns:
        El código de salida 0.
    """

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del export_store, purge
        use_case = ExportReviewedCrops(
            repository, crop_store, composition.build_training_store(config), clock
        )
        result = use_case.execute()
        sys.stdout.write(
            f"exportados={result.exported} omitidos={result.skipped} carpeta={result.path.name}\n"
        )
        return 0

    return commands._run_with_repository(config, commands.require_keys(args), action)
