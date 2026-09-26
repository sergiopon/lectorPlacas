from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from ocr_training.common import (
    DATASETS_DIR,
    RUNS_DIR,
    WEIGHTS_DIR,
    TrainingError,
    check_ocr_onnx,
    find_best_model,
    publish_model,
    require_asset,
    validate_annotations,
)

_NAME_REGEX: re.Pattern[str] = re.compile(r"^[a-z0-9_-]{1,40}$")


def _run_name(value: str) -> str:
    """Valida el nombre de la corrida (`--name`).

    Args:
        value: Valor recibido de la línea de comandos.

    Returns:
        El mismo valor, si es válido.

    Raises:
        argparse.ArgumentTypeError: si `value` no cumple `_NAME_REGEX`.
    """
    if not _NAME_REGEX.match(value):
        raise argparse.ArgumentTypeError(f"nombre de corrida inválido: {value!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del entrenamiento del OCR.

    Returns:
        Parser configurado con las opciones del comando.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--patience", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--name", type=_run_name, required=True)
    return parser


def train_arguments(
    args: argparse.Namespace, train_csv: Path, val_csv: Path, run_root: Path
) -> list[str]:
    """Construye los argumentos de la CLI `fast-plate-ocr train`.

    Args:
        args: Argumentos parseados (epochs, batch_size, patience, seed).
        train_csv: Ruta resuelta al CSV de entrenamiento.
        val_csv: Ruta resuelta al CSV de validación.
        run_root: Directorio de salida de la corrida.

    Returns:
        Lista de argumentos para `main_cli.main`.
    """
    return [
        "train",
        "--model-config-file",
        str(WEIGHTS_DIR / "cct_xs_v2_global_model_config.yaml"),
        "--plate-config-file",
        str(WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"),
        "--annotations",
        str(train_csv),
        "--val-annotations",
        str(val_csv),
        "--weights-path",
        str(WEIGHTS_DIR / "cct_xs_v2_global.keras"),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--early-stopping-patience",
        str(args.patience),
        "--seed",
        str(args.seed),
        "--validate-dataset",
        "error",
        "--output-dir",
        str(run_root),
    ]


def _resolve_within_datasets(path: Path) -> Path:
    """Resuelve un CSV de anotaciones dentro de `DATASETS_DIR`.

    Args:
        path: Ruta relativa a `DATASETS_DIR` (o absoluta dentro de ella).

    Returns:
        Ruta resuelta.

    Raises:
        TrainingError: si la ruta resuelta queda fuera de `DATASETS_DIR`.
    """
    resolved = (DATASETS_DIR / path).resolve()
    datasets_root = DATASETS_DIR.resolve()
    if datasets_root not in resolved.parents and resolved != datasets_root:
        raise TrainingError(f"ruta fuera de DATASETS_DIR: {path}")
    return resolved


# `fast_plate_ocr.cli.export.export` es un comando click suelto (no un grupo como
# `main_cli`), así que el nombre del subcomando no se consume: solo se reenvían los
# argumentos que van detrás de `export` (por eso `sys.argv[2:]`).
_EXPORT_SNIPPET: str = (
    "import sys; from fast_plate_ocr.cli.export import export; "
    "export.main(args=sys.argv[2:], standalone_mode=False)"
)


def _write_exportable_copy(best: Path, destination: Path) -> None:
    """Guarda una copia de `best` sin configuración de compilación.

    El `config.json` de un modelo entrenado con el backend torch referencia
    `keras.src.backend.torch.optimizers.torch_adamw`, lo que impide cargarlo con
    `KERAS_BACKEND=tensorflow` (el backend torch aborta el proceso). El optimizador
    no hace falta para exportar.

    Args:
        best: Ruta al `best.keras` de la corrida.
        destination: Ruta del `.keras` exportable a escribir.
    """
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    from fast_plate_ocr.train.utilities.utils import load_keras_model

    plate_config = load_plate_config_from_yaml(
        WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"
    )
    model = load_keras_model(best, plate_config)
    model.compiled = False
    model.save(destination)


def _export_onnx_arguments(model_path: Path, save_dir: Path) -> list[str]:
    """Construye los argumentos de la CLI `fast-plate-ocr export`.

    Args:
        model_path: `.keras` exportable (sin configuración de compilación).
        save_dir: Directorio de salida del `.onnx`.

    Returns:
        Lista de argumentos para el subcomando `export`.
    """
    return [
        "export",
        "--model",
        str(model_path),
        "--format",
        "onnx",
        "--plate-config-file",
        str(WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"),
        "--save-dir",
        str(save_dir),
    ]


def _export_onnx(best: Path) -> None:
    """Exporta el modelo a ONNX en un subproceso con backend TensorFlow.

    El export se hace con tf2onnx (TensorFlow) porque `torch.onnx` no soporta el
    kernel de `PatchExtractor` con lote dinámico. El subproceso oculta la GPU:
    TensorFlow 2.21 no encuentra sus librerías CUDA y grappler falla si intenta usarla.

    Args:
        best: Ruta al `best.keras` de la corrida.

    Raises:
        subprocess.CalledProcessError: si el subproceso de exportación falla.
    """
    with TemporaryDirectory() as staging:
        exportable = Path(staging) / "best.keras"
        _write_exportable_copy(best, exportable)
        subprocess.run(
            [
                sys.executable,
                "-c",
                _EXPORT_SNIPPET,
                *_export_onnx_arguments(exportable, best.parent),
            ],
            env={**os.environ, "KERAS_BACKEND": "tensorflow", "CUDA_VISIBLE_DEVICES": ""},
            check=True,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Entrena, exporta y publica el modelo OCR ajustado a placas colombianas.

    Args:
        argv: Argumentos de línea de comandos (por defecto `sys.argv[1:]`).

    Returns:
        Código de salida: 0 si el entrenamiento, la exportación y la
            verificación del modelo terminan correctamente.

    Raises:
        TrainingError: si las rutas de datos quedan fuera de `DATASETS_DIR`,
            si la corrida ya existe, si los recursos no están verificados o
            si el modelo exportado no pasa `check_ocr_onnx`.
    """
    args = build_parser().parse_args(argv)

    train_csv = _resolve_within_datasets(args.train)
    val_csv = _resolve_within_datasets(args.val)
    validate_annotations(train_csv)
    validate_annotations(val_csv)

    for name in (
        "cct_xs_v2_global.keras",
        "cct_xs_v2_global_model_config.yaml",
        "cct_xs_v2_global_plate_config.yaml",
    ):
        require_asset(name)

    run_root = RUNS_DIR / args.name
    if run_root.exists():
        raise TrainingError("la corrida ya existe")

    os.environ["KERAS_BACKEND"] = "torch"
    from fast_plate_ocr.cli.cli import main_cli

    main_cli.main(args=train_arguments(args, train_csv, val_csv, run_root), standalone_mode=False)

    best = find_best_model(run_root)
    _export_onnx(best)

    onnx_path = best.parent / "best.onnx"
    check_ocr_onnx(onnx_path)
    publish_model(onnx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
