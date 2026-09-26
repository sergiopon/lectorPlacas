# 032 - Entrenamiento: fine-tuning del OCR fast-plate-ocr con placas colombianas

## Objetivo
Crear el proyecto uv separado `training/ocr` con scripts para descargar los pesos Keras verificados,
fine-tunear `cct-xs-v2-global` con recortes colombianos (backend Keras = PyTorch cu130) y exportar a ONNX
compatible con el adaptador de la spec 017.

## Depende de
000 (repo), 031 (dataset `chars-to-ocr`, para el entrenamiento real).

## Archivos rectores aplicables
- ADR-003 (fine-tuning obligatorio), ADR-011 (proyecto separado, Python 3.13, cu130, override de protobuf), ADR-012 (hashes fijados).
- reglas-seguridad.md SEG-09/10 (datos reales solo locales; smoke test sintético), SEG-11 (`weights/`, `runs/`, `datasets/` ignorados), SEG-23.
- docs/04-evaluacion.md §5.3 (metas de cantidad), M-04 (CER ≤ 3 %).

## Archivos a crear/modificar
- `training/ocr/pyproject.toml`, `training/ocr/.python-version`
- `training/ocr/ocr_training/__init__.py`
- `training/ocr/ocr_training/common.py`
- `training/ocr/ocr_training/fetch_assets.py`
- `training/ocr/ocr_training/make_smoke_dataset.py`
- `training/ocr/ocr_training/train.py`
- `training/ocr/tests/test_common.py`
- `training/ocr/uv.lock` (generado)

## Dependencias externas
fast-plate-ocr[train]==1.1.0, torch==2.14.0 (índice cu130), keras==3.15.1, tensorflow==2.21.0, opencv-python==4.14.0.94,
onnx==1.23.0, onnxslim==0.1.96, onnxruntime-gpu==1.30.0, PyYAML==6.0.3, pillow==12.3.0 (usado por la spec 033); dev: pytest==9.1.1.

## Interfaces y tipos involucrados
API verificada de fast-plate-ocr 1.1.0:
```python
# CLI click: from fast_plate_ocr.cli.cli import main_cli   (console script "fast-plate-ocr")
# main_cli.main(args=[...], standalone_mode=False)
# train: --model-config-file, --plate-config-file, --annotations, --val-annotations (obligatorios);
#        --weights-path (carga con model.load_weights(..., skip_mismatch=True)), --epochs (150), --batch-size (64),
#        --output-dir, --seed, --early-stopping-patience (100), --validate-dataset {off,warn,error}
#        Guarda en <output-dir>/<AAAA-MM-DD_HH-MM-SS>/best.keras (y last.keras, model_config.yaml, plate_config.yaml)
#        Sin columna plate_region en el CSV la cabeza de región se desactiva.
# export: --model <best.keras> --format onnx --plate-config-file <yaml> --save-dir <dir existente>
#        salida <save-dir>/best.onnx; por defecto --simplify, --dynamic-batch, --onnx-input-dtype uint8,
#        --onnx-data-format channels_last  => entrada "input" uint8 [batch, 64, 128, 3], salida "plate"
# CSV: columnas image_path (relativa al CSV), plate_text; formato de cct_xs_v2_global_plate_config.yaml:
#        max_plate_slots 10, alfabeto 0-9A-Z + "_", 64x128, rgb
# Backend: variable KERAS_BACKEND=torch antes de importar keras
```
```python
# ocr_training/common.py — a implementar
TRAINING_DIR: Final[Path] = Path(__file__).resolve().parents[1]      # training/ocr
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
WEIGHTS_DIR: Final[Path] = TRAINING_DIR / "weights"
RUNS_DIR: Final[Path] = TRAINING_DIR / "runs"
DATASETS_DIR: Final[Path] = TRAINING_DIR / "datasets"
BASE_URL: Final[str] = "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates"
ASSETS: Final[Mapping[str, tuple[str, int]]] = MappingProxyType({
    "cct_xs_v2_global.keras": ("0716717772b1f8d25b3c227e1e65e7f42e63900ec017059b4a32155488735ffd", 10865307),
    "cct_xs_v2_global_model_config.yaml": ("e85d14b22bc6e68652375fa0d78e8e0ae5f69d4cca948962ccd77a79161c0358", 1351),
    "cct_xs_v2_global_plate_config.yaml": ("0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6", 1725),
})
OUTPUT_MODEL_ID: Final[str] = "fpo-cct-xs-v2-colombia"
PLATE_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{1,10}$")

class TrainingError(Exception): ...
def sha256_file(path: Path) -> str: ...
def require_asset(name: str) -> Path: ...
def validate_annotations(csv_path: Path) -> int: ...
def find_best_model(run_root: Path) -> Path: ...
def check_ocr_onnx(path: Path) -> None: ...
def publish_model(onnx_path: Path) -> Path: ...

# ocr_training/fetch_assets.py
def main() -> int: ...
# ocr_training/make_smoke_dataset.py
def make_smoke_dataset(output_dir: Path, train_count: int, val_count: int, seed: int) -> None: ...
def main(argv: Sequence[str] | None = None) -> int: ...
# ocr_training/train.py
def build_parser() -> argparse.ArgumentParser: ...
def train_arguments(args: argparse.Namespace, train_csv: Path, val_csv: Path, run_root: Path) -> list[str]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

## Comportamiento esperado
1. `pyproject.toml` **literal**:
```toml
[project]
name = "lector-placas-training-ocr"
version = "0.1.0"
requires-python = "==3.13.*"
dependencies = [
    "fast-plate-ocr[train]==1.1.0",
    "torch==2.14.0",
    "keras==3.15.1",
    "tensorflow==2.21.0",
    "opencv-python==4.14.0.94",
    "onnx==1.23.0",
    "onnxslim==0.1.96",
    "onnxruntime-gpu==1.30.0",
    "PyYAML==6.0.3",
    "pillow==12.3.0",
]

[dependency-groups]
dev = ["pytest==9.1.1"]

[tool.uv]
package = false
override-dependencies = [
    "opencv-python-headless; sys_platform == 'never'",
    "protobuf>=6.31.1,<8",
]

[tool.uv.sources]
torch = [{ index = "pytorch-cu130" }]

[[tool.uv.index]]
name = "pytorch-cu130"
url = "https://download.pytorch.org/whl/cu130"
explicit = true

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```
   `.python-version` = `3.13`.
2. `common.py`:
   - `sha256_file`: bloques de 1 MiB.
   - `require_asset(name)`: `name` debe estar en `ASSETS` (si no → `TrainingError`); `path = WEIGHTS_DIR / name`; inexistente, tamaño
     o SHA-256 distintos → `TrainingError("recurso no verificado: <name>; ejecute fetch_assets")`. Devuelve `path`.
   - `validate_annotations(csv)`: `csv.DictReader`; columnas exactamente `image_path` y `plate_text` (una columna `plate_region` →
     `TrainingError("plate_region no se usa: la cabeza de región queda desactivada")`); cada `plate_text` cumple `PLATE_TEXT_REGEX`;
     cada imagen `(csv.parent / image_path).resolve()` existe y está dentro de `csv.parent.resolve()`; sin filas → `TrainingError`.
     Devuelve el número de filas.
   - `find_best_model(run_root)`: subdirectorios de `run_root`; debe haber exactamente uno (si no → `TrainingError`) y contener `best.keras`.
   - `check_ocr_onnx(path)`: sesión ONNX Runtime en CPU; entrada 0 con nombre `input`, tipo `tensor(uint8)` y `shape[1:] == [64, 128, 3]`;
     alguna salida llamada `plate`; si no → `TrainingError("modelo OCR exportado incompatible")`.
   - `publish_model(onnx_path)`: copia a `PROJECT_ROOT / "models" / OUTPUT_MODEL_ID / f"{OUTPUT_MODEL_ID}.onnx"` (creando el directorio) e
     imprime `f"model_id={OUTPUT_MODEL_ID} filename={OUTPUT_MODEL_ID}.onnx sha256=<...> size_bytes=<...>"` y
     `"Copie sha256 y size_bytes en config/models.yaml"`. Devuelve el destino.
3. `fetch_assets.main()`: **única etapa con red**. `WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)`; por cada recurso de `ASSETS`: si ya existe
   verificado → se omite; si no, descarga `f"{BASE_URL}/{name}"` con `urllib.request.urlopen(url, timeout=60)` a `<name>.part`, verifica
   tamaño y SHA-256 (fallo → borra `.part` y `TrainingError`), `os.replace`. Devuelve 0.
4. `make_smoke_dataset(output_dir, train_count, val_count, seed)`: **datos 100 % sintéticos** para el smoke test. Genera textos aleatorios
   con `random.Random(seed)` alternando patrones `LLLDDD` y `LLLDDL`; cada imagen 64×128×3 `uint8` fondo `(0, 200, 255)` (BGR amarillo)
   con el texto en negro usando `cv2.putText(img, text, (4, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)`; guarda
   `output_dir/{train,val}/images/<i>.png` y `output_dir/{train,val}/annotations.csv` (`image_path,plate_text`, rutas `images/<i>.png`).
   `output_dir` debe estar dentro de `DATASETS_DIR` y no existir (si no → `TrainingError`).
   `main`: `--output` (relativo a `DATASETS_DIR`, por defecto `smoke`), `--train-count` (64), `--val-count` (16), `--seed` (0).
5. `train.py` — parser: `--train` y `--val` (Path, relativos a `DATASETS_DIR`, obligatorios), `--epochs` (int, 150), `--batch-size` (int, 64),
   `--patience` (int, 100), `--seed` (int, 0), `--name` (str, obligatorio, `^[a-z0-9_-]{1,40}$`).
   `train_arguments(args, train_csv, val_csv, run_root)` devuelve **exactamente**:
   `["train", "--model-config-file", str(WEIGHTS_DIR / "cct_xs_v2_global_model_config.yaml"), "--plate-config-file",
   str(WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"), "--annotations", str(train_csv), "--val-annotations", str(val_csv),
   "--weights-path", str(WEIGHTS_DIR / "cct_xs_v2_global.keras"), "--epochs", str(args.epochs), "--batch-size", str(args.batch_size),
   "--early-stopping-patience", str(args.patience), "--seed", str(args.seed), "--validate-dataset", "error", "--output-dir", str(run_root)]`.
   `main`:
   1. Resuelve `train_csv`/`val_csv` dentro de `DATASETS_DIR` (fuera → `TrainingError`); `validate_annotations` de ambos.
   2. `require_asset` de los tres recursos.
   3. `run_root = RUNS_DIR / args.name`; si existe → `TrainingError("la corrida ya existe")`.
   4. `os.environ["KERAS_BACKEND"] = "torch"` **antes** de importar `fast_plate_ocr.cli.cli` (import dentro de la función).
   5. `main_cli.main(args=train_arguments(...), standalone_mode=False)`.
   6. `best = find_best_model(run_root)`; `main_cli.main(args=["export", "--model", str(best), "--format", "onnx",
      "--plate-config-file", str(WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"), "--save-dir", str(best.parent)], standalone_mode=False)`.
   7. `onnx_path = best.parent / "best.onnx"`; `check_ocr_onnx(onnx_path)`; `publish_model(onnx_path)`. Devuelve 0.
6. Todos los módulos con `if __name__ == "__main__": raise SystemExit(main())`; se ejecutan desde `training/ocr` con
   `uv run python -m ocr_training.<modulo>`.
7. Para usar el modelo en runtime (operador, fuera de esta spec): añadir en `config/models.yaml` la entrada `fpo-cct-xs-v2-colombia`
   con el hash impreso y cambiar `models.ocr.model_id` en `config/lector.yaml`; `config_id` sigue siendo `fpo-cct-xs-v2-global-config`
   (el entrenamiento usa esa misma configuración de placa).

## Casos borde y manejo de errores
- **Detente y reporta la salida** (no cambies versiones ni overrides) si: `uv lock` no resuelve; el smoke test falla al cargar
  `--weights-path` o al entrenar con `KERAS_BACKEND=torch`; o `check_ocr_onnx` rechaza el modelo exportado.
- Los hiperparámetros por defecto son los de fast-plate-ocr y son **provisionales** (se ajustan con M-04).
- `.keras` se carga con Keras (formato zip de configuración + pesos), no con pickle.

## Tests de aceptación
```python
# training/ocr/tests/test_common.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from ocr_training.common import (
    TrainingError, check_ocr_onnx, find_best_model, sha256_file, validate_annotations,
)
from ocr_training.train import build_parser, train_arguments


def ocr_model(path: Path, input_name: str = "input", dtype: int = TensorProto.UINT8,
              output_name: str = "plate") -> Path:
    value = numpy_helper.from_array(np.zeros((1, 370), dtype=np.float32), name="v")
    node = helper.make_node("Constant", [], [output_name], value=value)
    graph = helper.make_graph(
        [node], "g", [helper.make_tensor_value_info(input_name, dtype, ["batch", 64, 128, 3])],
        [helper.make_tensor_value_info(output_name, TensorProto.FLOAT, [1, 370])])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def write_csv(root: Path, body: str, images: tuple[str, ...] = ("a.png",)) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    for name in images:
        (root / "images" / name).write_bytes(b"png")
    path = root / "annotations.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_sha256(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_validate_annotations(tmp_path: Path) -> None:
    assert validate_annotations(write_csv(tmp_path / "ok", "image_path,plate_text\nimages/a.png,ABC123\n")) == 1


@pytest.mark.parametrize("body", [
    "image_path,plate_text,plate_region\nimages/a.png,ABC123,Colombia\n",
    "image_path,plate_text\nimages/a.png,abc123\n",
    "image_path,plate_text\nimages/missing.png,ABC123\n",
    "image_path,plate_text\n../a.png,ABC123\n",
    "image_path,plate_text\n",
])
def test_validate_annotations_errors(tmp_path: Path, body: str) -> None:
    with pytest.raises(TrainingError):
        validate_annotations(write_csv(tmp_path / "bad", body))


def test_find_best_model(tmp_path: Path) -> None:
    with pytest.raises(TrainingError):
        find_best_model(tmp_path)
    run = tmp_path / "2026-09-26_10-00-00"
    run.mkdir()
    (run / "best.keras").write_bytes(b"k")
    assert find_best_model(tmp_path) == run / "best.keras"


def test_check_ocr_onnx(tmp_path: Path) -> None:
    check_ocr_onnx(ocr_model(tmp_path / "ok.onnx"))
    with pytest.raises(TrainingError):
        check_ocr_onnx(ocr_model(tmp_path / "f.onnx", dtype=TensorProto.FLOAT))
    with pytest.raises(TrainingError):
        check_ocr_onnx(ocr_model(tmp_path / "o.onnx", output_name="logits"))


def test_train_arguments(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--train", "a.csv", "--val", "b.csv", "--name", "run1"])
    result = train_arguments(args, tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "run1")
    assert result[0] == "train"
    assert result[result.index("--epochs") + 1] == "150"
    assert result[result.index("--validate-dataset") + 1] == "error"
    assert result[result.index("--output-dir") + 1] == str(tmp_path / "run1")
    assert result[result.index("--weights-path") + 1].endswith("cct_xs_v2_global.keras")
```

## Fuera de alcance
Preparar el dataset real (spec 031); placas sintéticas de calidad para entrenamiento (spec 033); exportar TFLite/CoreML (futuro móvil).

## Definition of Done
- [ ] En `training/ocr`: `uv lock`, `uv sync --locked` y `uv run pytest` en verde.
- [ ] `uv run python -c "import torch; print(torch.cuda.get_device_capability())"` imprime `(12, 0)`.
- [ ] `uv run python -m ocr_training.fetch_assets` termina con código 0.
- [ ] Smoke test: `uv run python -m ocr_training.make_smoke_dataset` y
      `uv run python -m ocr_training.train --train smoke/train/annotations.csv --val smoke/val/annotations.csv --epochs 1 --batch-size 16 --name smoke`
      terminan con código 0 y publican `models/fpo-cct-xs-v2-colombia/fpo-cct-xs-v2-colombia.onnx` (este modelo de smoke **no** se registra en el manifiesto).
- [ ] `git status` no muestra `weights/`, `runs/` ni `datasets/`.
