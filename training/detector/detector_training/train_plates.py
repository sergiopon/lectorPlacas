from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from detector_training.common import (
    BASE_WEIGHTS_PATH,
    BASE_WEIGHTS_SHA256,
    DATASETS_DIR,
    RUNS_DIR,
    TrainingError,
    check_end2end_onnx,
    publish_model,
    require_sha256,
    set_offline_env,
    sha256_file,
    validate_single_class_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del entrenamiento del detector de placas.

    Returns:
        Parser configurado con los hiperparámetros de entrenamiento.
    """
    parser = argparse.ArgumentParser(description="Entrena el detector de placas colombianas")
    parser.add_argument("--data", type=Path, required=True, help="Ruta relativa a DATASETS_DIR")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--name", type=str, default="plates-yolo26n")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entrena el detector de placas y exporta el mejor checkpoint a ONNX end2end.

    Args:
        argv: Argumentos de línea de comandos; `None` usa `sys.argv`.

    Returns:
        Código de salida: 0 si el entrenamiento y la exportación terminan sin error.

    Raises:
        TrainingError: si `data` está fuera de `DATASETS_DIR`, el dataset no es
            de una sola clase, los pesos base no coinciden con su hash, o no se
            produce `best.pt`.
    """
    args = build_parser().parse_args(argv)

    data = (DATASETS_DIR / args.data).resolve()
    if not data.is_relative_to(DATASETS_DIR.resolve()):
        raise TrainingError(f"dataset fuera de DATASETS_DIR: {data}")
    validate_single_class_dataset(data)

    set_offline_env()
    from ultralytics import YOLO  # noqa: PLC0415 (offline env debe fijarse antes del import)

    require_sha256(BASE_WEIGHTS_PATH, BASE_WEIGHTS_SHA256)
    model = YOLO(str(BASE_WEIGHTS_PATH))
    model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        seed=0,
        deterministic=True,
        project=str(RUNS_DIR.resolve()),
        name=args.name,
        exist_ok=False,
    )

    best = Path(model.trainer.best)
    if not best.is_file():
        raise TrainingError(f"no se produjo best.pt: {best}")
    print(f"best.pt sha256={sha256_file(best)}")

    out = YOLO(str(best)).export(
        format="onnx", imgsz=args.imgsz, nms=False, dynamic=False, simplify=True, device="cpu"
    )
    check_end2end_onnx(Path(out), args.imgsz)
    publish_model(Path(out), "yolo26n-plates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
