from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Final

import onnxruntime
import yaml

TRAINING_DIR: Final[Path] = Path(__file__).resolve().parents[1]
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
WEIGHTS_DIR: Final[Path] = TRAINING_DIR / "weights"
RUNS_DIR: Final[Path] = TRAINING_DIR / "runs"
DATASETS_DIR: Final[Path] = TRAINING_DIR / "datasets"
BASE_WEIGHTS_URL: Final[str] = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
BASE_WEIGHTS_SHA256: Final[str] = "9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef"
BASE_WEIGHTS_SIZE: Final[int] = 5544453
BASE_WEIGHTS_PATH: Final[Path] = WEIGHTS_DIR / "yolo26n.pt"
END2END_ROWS: Final[int] = 300

_CHUNK_SIZE: Final[int] = 1024 * 1024


class TrainingError(Exception):
    """Error del pipeline de entrenamiento del detector."""


def sha256_file(path: Path) -> str:
    """Calcula el SHA-256 de un archivo leyendo en bloques de 1 MiB.

    Args:
        path: Ruta del archivo a hashear.

    Returns:
        Hash SHA-256 en hexadecimal.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(path: Path, expected: str) -> None:
    """Verifica que un archivo exista y tenga el SHA-256 esperado.

    Args:
        path: Ruta del archivo a verificar.
        expected: SHA-256 hexadecimal esperado.

    Raises:
        TrainingError: si el archivo no existe o el hash no coincide.
    """
    if not path.is_file() or sha256_file(path) != expected:
        raise TrainingError(f"hash no coincide: {path.name}")


def set_offline_env() -> None:
    """Configura las variables de entorno para que Ultralytics no acceda a la red."""
    os.environ["YOLO_OFFLINE"] = "True"
    os.environ["YOLO_AUTOINSTALL"] = "False"


def check_end2end_onnx(path: Path, input_size: int) -> None:
    """Verifica que un modelo ONNX exportado sea end2end (cabeza sin NMS externo).

    Args:
        path: Ruta del archivo ONNX.
        input_size: Lado (alto = ancho) esperado de la entrada.

    Raises:
        TrainingError: si el nombre de entrada, la forma de entrada o la forma
            de salida no coinciden con lo esperado.
    """
    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    expected_input_shape = [1, 3, input_size, input_size]
    expected_output_shape = [1, END2END_ROWS, 6]
    input_ok = inputs[0].name == "images" and list(inputs[0].shape) == expected_input_shape
    output_ok = list(outputs[0].shape) == expected_output_shape
    if not (input_ok and output_ok):
        raise TrainingError(f"salida ONNX inesperada: {outputs[0].shape}")


def validate_single_class_dataset(data_yaml: Path) -> None:
    """Verifica que el dataset YOLO declare una única clase llamada 'plate'.

    Args:
        data_yaml: Ruta al archivo `data.yaml` del dataset.

    Raises:
        TrainingError: si `names` no es `{0: "plate"}` ni `["plate"]`.
    """
    data = yaml.safe_load(data_yaml.read_text())
    names = data.get("names") if isinstance(data, dict) else None
    if names != {0: "plate"} and names != ["plate"]:
        raise TrainingError(f"dataset no es de una sola clase 'plate': {names!r}")


def publish_model(onnx_path: Path, model_id: str) -> Path:
    """Copia el modelo ONNX exportado a `models/<model_id>/` e imprime su hash.

    Args:
        onnx_path: Ruta del archivo ONNX exportado.
        model_id: Identificador del modelo (nombre del subdirectorio y del archivo).

    Returns:
        Ruta de destino del archivo copiado.
    """
    destination_dir = PROJECT_ROOT / "models" / model_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{model_id}.onnx"
    shutil.copyfile(onnx_path, destination)
    sha256 = sha256_file(destination)
    size_bytes = destination.stat().st_size
    print(f"model_id={model_id} filename={model_id}.onnx sha256={sha256} size_bytes={size_bytes}")
    print("Copie sha256 y size_bytes en config/models.yaml")
    return destination
