from __future__ import annotations

import csv
import hashlib
import re
import shutil
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

TRAINING_DIR: Final[Path] = Path(__file__).resolve().parents[1]
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
WEIGHTS_DIR: Final[Path] = TRAINING_DIR / "weights"
RUNS_DIR: Final[Path] = TRAINING_DIR / "runs"
DATASETS_DIR: Final[Path] = TRAINING_DIR / "datasets"
BASE_URL: Final[str] = "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates"
ASSETS: Final[Mapping[str, tuple[str, int]]] = MappingProxyType(
    {
        "cct_xs_v2_global.keras": (
            "0716717772b1f8d25b3c227e1e65e7f42e63900ec017059b4a32155488735ffd",
            10865307,
        ),
        "cct_xs_v2_global_model_config.yaml": (
            "e85d14b22bc6e68652375fa0d78e8e0ae5f69d4cca948962ccd77a79161c0358",
            1351,
        ),
        "cct_xs_v2_global_plate_config.yaml": (
            "0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6",
            1725,
        ),
    }
)
OUTPUT_MODEL_ID: Final[str] = "fpo-cct-xs-v2-colombia"
PLATE_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{1,10}$")

_CHUNK_SIZE: Final[int] = 1024 * 1024
_EXPECTED_COLUMNS: Final[frozenset[str]] = frozenset({"image_path", "plate_text"})
_EXPECTED_INPUT_SHAPE: Final[list[int]] = [64, 128, 3]


class TrainingError(Exception):
    """Error del pipeline de entrenamiento del OCR."""


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


def require_asset(name: str) -> Path:
    """Verifica que un recurso descargado exista y coincida con `ASSETS`.

    Args:
        name: Nombre del recurso, debe estar en `ASSETS`.

    Returns:
        Ruta del recurso verificado en `WEIGHTS_DIR`.

    Raises:
        TrainingError: si `name` no está en `ASSETS` o el archivo no existe, no
            coincide en tamaño o no coincide en SHA-256.
    """
    if name not in ASSETS:
        raise TrainingError(f"recurso desconocido: {name}")
    expected_sha256, expected_size = ASSETS[name]
    path = WEIGHTS_DIR / name
    if (
        not path.is_file()
        or path.stat().st_size != expected_size
        or sha256_file(path) != expected_sha256
    ):
        raise TrainingError(f"recurso no verificado: {name}; ejecute fetch_assets")
    return path


def validate_annotations(csv_path: Path) -> int:
    """Valida un CSV de anotaciones para el entrenamiento del OCR.

    Args:
        csv_path: Ruta al archivo `annotations.csv`.

    Returns:
        Número de filas válidas.

    Raises:
        TrainingError: si las columnas no son exactamente `image_path` y
            `plate_text`, si hay una columna `plate_region`, si algún
            `plate_text` no cumple `PLATE_TEXT_REGEX`, si alguna imagen
            referenciada no existe o queda fuera del directorio del CSV, o si
            el CSV no tiene filas.
    """
    csv_root = csv_path.parent.resolve()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = frozenset(reader.fieldnames or ())
        if "plate_region" in columns:
            raise TrainingError("plate_region no se usa: la cabeza de región queda desactivada")
        if columns != _EXPECTED_COLUMNS:
            raise TrainingError(f"columnas inválidas: {sorted(columns)}")
        count = 0
        for row in reader:
            plate_text = row["plate_text"]
            if not PLATE_TEXT_REGEX.match(plate_text):
                raise TrainingError(f"plate_text inválido: {plate_text!r}")
            image_path = (csv_path.parent / row["image_path"]).resolve()
            if csv_root not in image_path.parents and image_path != csv_root:
                raise TrainingError(f"imagen fuera del directorio del CSV: {row['image_path']}")
            if not image_path.is_file():
                raise TrainingError(f"imagen inexistente: {row['image_path']}")
            count += 1
    if count == 0:
        raise TrainingError(f"sin filas: {csv_path}")
    return count


def find_best_model(run_root: Path) -> Path:
    """Localiza el `best.keras` de la única corrida bajo `run_root`.

    Args:
        run_root: Directorio de salida del entrenamiento (`--output-dir`).

    Returns:
        Ruta al archivo `best.keras`.

    Raises:
        TrainingError: si no hay exactamente un subdirectorio o si no contiene
            `best.keras`.
    """
    subdirs = [child for child in run_root.iterdir() if child.is_dir()] if run_root.is_dir() else []
    if len(subdirs) != 1:
        raise TrainingError(f"se esperaba exactamente una corrida en {run_root}")
    best = subdirs[0] / "best.keras"
    if not best.is_file():
        raise TrainingError(f"best.keras no encontrado en {subdirs[0]}")
    return best


def check_ocr_onnx(path: Path) -> None:
    """Verifica la forma de entrada/salida del modelo OCR exportado a ONNX.

    Args:
        path: Ruta al archivo ONNX exportado.

    Raises:
        TrainingError: si la entrada 0 no se llama `input`, no es
            `tensor(uint8)` o no tiene forma `[*, 64, 128, 3]`, o si ninguna
            salida se llama `plate`.
    """
    import onnxruntime

    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    input_ok = (
        bool(inputs)
        and inputs[0].name == "input"
        and inputs[0].type == "tensor(uint8)"
        and list(inputs[0].shape[1:]) == _EXPECTED_INPUT_SHAPE
    )
    output_ok = any(output.name == "plate" for output in outputs)
    if not (input_ok and output_ok):
        raise TrainingError("modelo OCR exportado incompatible")


def publish_model(onnx_path: Path) -> Path:
    """Copia el modelo ONNX exportado a `models/<OUTPUT_MODEL_ID>/` e imprime su hash.

    Args:
        onnx_path: Ruta del archivo ONNX exportado.

    Returns:
        Ruta de destino del archivo copiado.
    """
    destination_dir = PROJECT_ROOT / "models" / OUTPUT_MODEL_ID
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{OUTPUT_MODEL_ID}.onnx"
    shutil.copyfile(onnx_path, destination)
    sha256 = sha256_file(destination)
    size_bytes = destination.stat().st_size
    print(
        f"model_id={OUTPUT_MODEL_ID} filename={OUTPUT_MODEL_ID}.onnx sha256={sha256} size_bytes={size_bytes}"
    )
    print("Copie sha256 y size_bytes en config/models.yaml")
    return destination
