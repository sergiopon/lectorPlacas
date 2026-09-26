# 030 - Entrenamiento: entorno del detector, exportación ONNX y fine-tuning de placas

## Objetivo
Crear el proyecto uv separado `training/detector` (PyTorch cu130 + Ultralytics) con scripts para:
descargar `yolo26n.pt` verificado, exportar el detector COCO a ONNX end2end y entrenar/exportar el
detector de placas colombianas.

## Depende de
000 (para el repo), 031 (dataset de placas, solo para el paso de entrenamiento).

## Archivos rectores aplicables
- ADR-001 (salida end2end `[1, 300, 6]`), ADR-002, ADR-008 (AGPL), ADR-011 (proyecto uv separado, cu130, Python 3.13), ADR-012 (hash fijado).
- reglas-seguridad.md SEG-11 (`weights/`, `runs/`, `datasets/` ignorados), SEG-18 (solo `yolo26n.pt` verificado y checkpoints locales),
  SEG-22 (`YOLO_OFFLINE=True`, `YOLO_AUTOINSTALL=False`), SEG-23 (versiones fijadas + lock).

## Archivos a crear/modificar
- `training/detector/pyproject.toml`
- `training/detector/.python-version`
- `training/detector/detector_training/__init__.py`
- `training/detector/detector_training/common.py`
- `training/detector/detector_training/fetch_base_weights.py`
- `training/detector/detector_training/export_coco.py`
- `training/detector/detector_training/train_plates.py`
- `training/detector/tests/test_common.py`
- `training/detector/uv.lock` (generado)

## Dependencias externas
torch==2.14.0 y torchvision==0.29.0 (índice `https://download.pytorch.org/whl/cu130`), ultralytics==8.4.162,
onnx==1.23.0, onnxslim==0.1.96, onnxruntime-gpu==1.30.0, PyYAML==6.0.3; dev: pytest==9.1.1.

## Interfaces y tipos involucrados
API verificada de Ultralytics 8.4.162:
```python
# from ultralytics import YOLO
# YOLO(path_str).export(format="onnx", imgsz=640, nms=False, dynamic=False, simplify=True, device="cpu") -> str   # ruta del .onnx
#   nms=False => cabeza sin NMS (end2end en YOLO26): entrada "images" [1,3,S,S], salida "output0" [1,300,6]
# YOLO(path_str).train(data=..., epochs=..., imgsz=..., batch=..., device=..., seed=0, deterministic=True,
#                      project=str_abs, name=str, exist_ok=False, workers=...)
# model.trainer.best -> Path a <project>/<name>/weights/best.pt
# Variables: YOLO_OFFLINE / YOLO_AUTOINSTALL se leen con env_bool ("true", "1", ... = verdadero; otro valor = falso)
```
```python
# detector_training/common.py — a implementar
TRAINING_DIR: Final[Path] = Path(__file__).resolve().parents[1]      # training/detector
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]      # raíz del repo
WEIGHTS_DIR: Final[Path] = TRAINING_DIR / "weights"
RUNS_DIR: Final[Path] = TRAINING_DIR / "runs"
DATASETS_DIR: Final[Path] = TRAINING_DIR / "datasets"
BASE_WEIGHTS_URL: Final[str] = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
BASE_WEIGHTS_SHA256: Final[str] = "9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef"
BASE_WEIGHTS_SIZE: Final[int] = 5544453
BASE_WEIGHTS_PATH: Final[Path] = WEIGHTS_DIR / "yolo26n.pt"
END2END_ROWS: Final[int] = 300

class TrainingError(Exception): ...
def sha256_file(path: Path) -> str: ...
def require_sha256(path: Path, expected: str) -> None: ...
def set_offline_env() -> None: ...
def check_end2end_onnx(path: Path, input_size: int) -> None: ...
def validate_single_class_dataset(data_yaml: Path) -> None: ...
def publish_model(onnx_path: Path, model_id: str) -> Path: ...

# detector_training/fetch_base_weights.py
def main() -> int: ...
# detector_training/export_coco.py
def main() -> int: ...
# detector_training/train_plates.py
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

## Comportamiento esperado
1. `pyproject.toml` **literal**:
```toml
[project]
name = "lector-placas-training-detector"
version = "0.1.0"
requires-python = "==3.13.*"
dependencies = [
    "torch==2.14.0",
    "torchvision==0.29.0",
    "ultralytics==8.4.162",
    "onnx==1.23.0",
    "onnxslim==0.1.96",
    "onnxruntime-gpu==1.30.0",
    "PyYAML==6.0.3",
]

[dependency-groups]
dev = ["pytest==9.1.1"]

[tool.uv]
package = false
override-dependencies = ["opencv-python-headless; sys_platform == 'never'"]

[tool.uv.sources]
torch = [{ index = "pytorch-cu130" }]
torchvision = [{ index = "pytorch-cu130" }]

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
   - `sha256_file`: bloques de 1 MiB. `require_sha256(path, expected)`: inexistente o hash distinto → `TrainingError("hash no coincide: <nombre>")`.
   - `set_offline_env()`: `os.environ["YOLO_OFFLINE"] = "True"`; `os.environ["YOLO_AUTOINSTALL"] = "False"`.
   - `check_end2end_onnx(path, s)`: `onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])`;
     exige `inputs[0].name == "images"`, `inputs[0].shape == [1, 3, s, s]` y `outputs[0].shape == [1, END2END_ROWS, 6]`;
     si no → `TrainingError("salida ONNX inesperada: <shape>")`.
   - `validate_single_class_dataset(data_yaml)`: `yaml.safe_load`; `names` debe ser `{0: "plate"}` o `["plate"]`; si no → `TrainingError`.
   - `publish_model(onnx_path, model_id)`: destino `PROJECT_ROOT / "models" / model_id / f"{model_id}.onnx"`; crea el directorio
     (`mkdir(parents=True, exist_ok=True)`), `shutil.copyfile`; imprime (esto son scripts de consola)
     `f"model_id={model_id} filename={model_id}.onnx sha256={...} size_bytes={...}"` y
     `"Copie sha256 y size_bytes en config/models.yaml"`. Devuelve el destino.
3. `fetch_base_weights.main()`: **única etapa con red**. Si `BASE_WEIGHTS_PATH` existe con el hash correcto → imprime "ya descargado" y devuelve 0.
   Si no: `WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)`; descarga `BASE_WEIGHTS_URL` con `urllib.request.urlopen(url, timeout=60)`
   a `yolo26n.pt.part` en bloques de 1 MiB; verifica tamaño `BASE_WEIGHTS_SIZE` y SHA-256; si falla borra el `.part` y lanza
   `TrainingError`; si no `os.replace`. Devuelve 0.
4. `export_coco.main()`: `set_offline_env()` **antes** de importar Ultralytics (import dentro de la función);
   `require_sha256(BASE_WEIGHTS_PATH, BASE_WEIGHTS_SHA256)`; `out = YOLO(str(BASE_WEIGHTS_PATH)).export(format="onnx", imgsz=640, nms=False, dynamic=False, simplify=True, device="cpu")`;
   `check_end2end_onnx(Path(out), 640)`; `publish_model(Path(out), "yolo26n-coco")`. Devuelve 0.
5. `train_plates`: parser con `--data` (Path, obligatorio, relativo a `DATASETS_DIR`), `--epochs` (int, 100), `--batch` (int, 16),
   `--imgsz` (int, 640), `--device` (str, "0"), `--workers` (int, 8), `--name` (str, "plates-yolo26n").
   `main`: `data = (DATASETS_DIR / args.data).resolve()`; si no está dentro de `DATASETS_DIR.resolve()` → `TrainingError`;
   `validate_single_class_dataset(data)`; `set_offline_env()`; `require_sha256(BASE_WEIGHTS_PATH, BASE_WEIGHTS_SHA256)`;
   `model = YOLO(str(BASE_WEIGHTS_PATH))`; `model.train(data=str(data), epochs=..., imgsz=..., batch=..., device=..., workers=...,
   seed=0, deterministic=True, project=str(RUNS_DIR.resolve()), name=args.name, exist_ok=False)`;
   `best = Path(model.trainer.best)`; inexistente → `TrainingError`; imprime `f"best.pt sha256={sha256_file(best)}"`;
   `out = YOLO(str(best)).export(format="onnx", imgsz=args.imgsz, nms=False, dynamic=False, simplify=True, device="cpu")`;
   `check_end2end_onnx(Path(out), args.imgsz)`; `publish_model(Path(out), "yolo26n-plates")`. Devuelve 0.
6. Los tres módulos terminan con `if __name__ == "__main__": raise SystemExit(main())` y se ejecutan desde `training/detector`
   con `uv run python -m detector_training.<modulo>`.
7. El valor por defecto de los hiperparámetros (100 épocas, batch 16, 640 px) es el de Ultralytics (`cfg/default.yaml`) y es
   **provisional**; se ajusta con la evaluación de Fase 5.

## Casos borde y manejo de errores
- Si `uv lock` no resuelve, si `torch.cuda.get_device_capability()` no es `(12, 0)`, o si `check_end2end_onnx` falla con el modelo
  real: **detente y reporta la salida**; no cambies versiones ni parámetros de exportación.
- Ningún script carga `.pt` distintos de `yolo26n.pt` verificado o del `best.pt` recién producido.

## Tests de aceptación
```python
# training/detector/tests/test_common.py
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import onnx
import pytest
import yaml
from onnx import TensorProto, helper, numpy_helper

from detector_training.common import (
    TrainingError, check_end2end_onnx, require_sha256, set_offline_env, sha256_file,
    validate_single_class_dataset,
)


def constant_model(path: Path, shape: tuple[int, ...], size: int = 64) -> Path:
    value = numpy_helper.from_array(np.zeros(shape, dtype=np.float32), name="v")
    node = helper.make_node("Constant", [], ["output0"], value=value)
    graph = helper.make_graph(
        [node], "g", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, size, size])],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(shape))])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def test_sha_helpers(tmp_path: Path) -> None:
    path = tmp_path / "w.pt"
    path.write_bytes(b"pesos")
    digest = hashlib.sha256(b"pesos").hexdigest()
    assert sha256_file(path) == digest
    require_sha256(path, digest)
    with pytest.raises(TrainingError):
        require_sha256(path, "0" * 64)
    with pytest.raises(TrainingError):
        require_sha256(tmp_path / "no.pt", digest)


def test_offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOLO_OFFLINE", raising=False)
    monkeypatch.delenv("YOLO_AUTOINSTALL", raising=False)
    set_offline_env()
    assert (os.environ["YOLO_OFFLINE"], os.environ["YOLO_AUTOINSTALL"]) == ("True", "False")


def test_check_end2end_onnx(tmp_path: Path) -> None:
    check_end2end_onnx(constant_model(tmp_path / "ok.onnx", (1, 300, 6)), 64)
    with pytest.raises(TrainingError):
        check_end2end_onnx(constant_model(tmp_path / "bad.onnx", (1, 84, 8400)), 64)
    with pytest.raises(TrainingError):
        check_end2end_onnx(constant_model(tmp_path / "size.onnx", (1, 300, 6), size=32), 64)


@pytest.mark.parametrize("names,ok", [
    ({0: "plate"}, True), (["plate"], True), (["placa"], False), (["plate", "car"], False),
])
def test_validate_single_class_dataset(tmp_path: Path, names: object, ok: bool) -> None:
    data = tmp_path / "data.yaml"
    data.write_text(yaml.safe_dump({"path": ".", "train": "images/train", "val": "images/val", "names": names}))
    if ok:
        validate_single_class_dataset(data)
    else:
        with pytest.raises(TrainingError):
            validate_single_class_dataset(data)
```

## Fuera de alcance
Preparar el dataset (spec 031); actualizar `config/models.yaml` (lo hace el operador con la salida impresa); cambiar
`models.plate_detector.backend` a `yolo` en `config/lector.yaml` (decisión del operador tras evaluar).

## Definition of Done
- [ ] En `training/detector`: `uv lock`, `uv sync --locked` y `uv run pytest` en verde.
- [ ] `uv run python -c "import torch; print(torch.__version__, torch.cuda.get_device_capability())"` imprime `2.14.0+cu130 (12, 0)`.
- [ ] `uv run python -m detector_training.fetch_base_weights` y `uv run python -m detector_training.export_coco` terminan con código 0
      e imprimen el SHA-256 de `yolo26n-coco.onnx`.
- [ ] (Operador) hash copiado en `config/models.yaml` y, en la raíz, `uv run lector models verify` muestra `yolo26n-coco: ok`.
- [ ] `git status` no muestra `weights/`, `runs/` ni `datasets/`.
