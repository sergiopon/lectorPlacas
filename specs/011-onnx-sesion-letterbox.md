# 011 - Adaptador: sesión ONNX Runtime y letterbox

## Objetivo
Crear sesiones de ONNX Runtime (CUDA o CPU) de forma uniforme y proveer el pre/post-procesamiento
letterbox usado por los modelos YOLO.

## Depende de
001, 005.

## Archivos rectores aplicables
- ADR-009 (ONNX Runtime, `preload_dlls(directory="")`, proveedores). SEG-17/19 (la ruta la entrega el registro de modelos).
- ARQUITECTURA.md §6 (excepciones de librería envueltas).

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/onnx_session.py`
- `src/lector_placas/adapters/inference/letterbox.py`
- `tests/fixtures/synthetic_onnx.py`
- `tests/unit/adapters/test_letterbox.py`
- `tests/integration/test_onnx_session.py`

## Dependencias externas
onnxruntime-gpu[cuda,cudnn]==1.30.0, opencv-python==4.14.0.94, numpy==2.5.3; dev: onnx==1.23.0 (solo tests).

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
ImageBGR: TypeAlias = npt.NDArray[np.uint8]
# de domain/entities.py
@dataclass(frozen=True, slots=True)
class BoundingBox: x1: float; y1: float; x2: float; y2: float   # clip(w, h) -> BoundingBox | None
# de domain/errors.py
class ModelLoadError(LectorPlacasError): ...
class InferenceError(LectorPlacasError): ...
```
```python
# adapters/inference/onnx_session.py — a implementar
ExecutionProvider: TypeAlias = Literal["cuda", "cpu"]
ORT_ERRORS: Final[tuple[type[BaseException], ...]]   # ver paso 1

class InferenceSessionLike(Protocol):
    def run(self, output_names: list[str] | None,
            input_feed: dict[str, npt.NDArray[Any]]) -> list[npt.NDArray[Any]]: ...

def providers_for(execution_provider: ExecutionProvider) -> list[str]: ...
def create_session(model_path: Path, execution_provider: ExecutionProvider) -> InferenceSessionLike: ...

# adapters/inference/letterbox.py — a implementar
PAD_VALUE: Final[int] = 114

@dataclass(frozen=True, slots=True)
class LetterboxTransform:
    scale: float
    pad_x: int
    pad_y: int
    source_width: int
    source_height: int

def letterbox(image: ImageBGR, size: int) -> tuple[ImageBGR, LetterboxTransform]: ...
def to_model_input(letterboxed: ImageBGR) -> npt.NDArray[np.float32]: ...
def box_to_source(x1: float, y1: float, x2: float, y2: float,
                  transform: LetterboxTransform) -> BoundingBox | None: ...
```

## Comportamiento esperado
1. `ORT_ERRORS` = tupla con `RuntimeError`, `OSError`, `ValueError` y las clases de
   `onnxruntime.capi.onnxruntime_pybind11_state`: `Fail`, `InvalidArgument`, `NoSuchFile`, `NoModel`,
   `EngineError`, `RuntimeException`, `InvalidProtobuf`, `NotImplemented`, `InvalidGraph`, `EPFail`
   (estas heredan de `Exception` directamente, por eso se enumeran).
2. `providers_for("cuda")` → `["CUDAExecutionProvider", "CPUExecutionProvider"]`; `providers_for("cpu")` → `["CPUExecutionProvider"]`.
3. `create_session(model_path, ep)`:
   - Si `ep == "cuda"`: llama `_preload_cuda_libraries()` (función privada decorada con `@functools.cache`
     que ejecuta `onnxruntime.preload_dlls(directory="")`); si `"CUDAExecutionProvider"` no está en
     `onnxruntime.get_available_providers()` → `ModelLoadError("CUDA no disponible en ONNX Runtime")`.
   - `onnxruntime.InferenceSession(str(model_path), providers=providers_for(ep))`; cualquier `ORT_ERRORS`
     → `ModelLoadError("no se pudo cargar el modelo: <model_path.name>") from e`.
4. `letterbox(image, size)`: `h, w = image.shape[:2]`; `scale = min(size / w, size / h)`;
   `new_w = max(1, round(w * scale))`, `new_h = max(1, round(h * scale))`;
   `resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)`;
   `pad_x = (size - new_w) // 2`, `pad_y = (size - new_h) // 2`;
   lienzo `np.full((size, size, 3), PAD_VALUE, np.uint8)` con `resized` en `[pad_y:pad_y+new_h, pad_x:pad_x+new_w]`.
   Devuelve `(lienzo, LetterboxTransform(scale, pad_x, pad_y, w, h))`.
5. `to_model_input(img)`: BGR→RGB (`img[:, :, ::-1]`), `float32 / 255.0`, HWC→CHW, añade eje batch;
   devuelve arreglo C-contiguo de forma `(1, 3, S, S)`.
6. `box_to_source(x1, y1, x2, y2, t)`: `sx = (x - t.pad_x) / t.scale`, `sy = (y - t.pad_y) / t.scale`;
   recorta a `[0, source_width] × [0, source_height]`; si no es finito o queda vacía → `None`; si no `BoundingBox`.

## Casos borde y manejo de errores
- `letterbox` con `size <= 0` → `InferenceError("tamaño de entrada inválido")`.

## Tests de aceptación
```python
# tests/fixtures/synthetic_onnx.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def constant_output_model(path: Path, output: np.ndarray, input_size: int = 64) -> Path:
    """Modelo ONNX sintético: ignora la entrada `images` y devuelve `output0` constante."""
    value = numpy_helper.from_array(output.astype(np.float32), name="const_value")
    node = helper.make_node("Constant", inputs=[], outputs=["output0"], value=value)
    graph = helper.make_graph(
        [node], "synthetic",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, input_size, input_size])],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(output.shape))],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path
```
```python
# tests/unit/adapters/test_letterbox.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.adapters.inference.letterbox import (
    PAD_VALUE, box_to_source, letterbox, to_model_input,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError


def test_letterbox_wide_image() -> None:
    image = np.full((100, 200, 3), 50, dtype=np.uint8)
    canvas, t = letterbox(image, 64)
    assert canvas.shape == (64, 64, 3)
    assert (t.scale, t.pad_x, t.pad_y, t.source_width, t.source_height) == (0.32, 0, 16, 200, 100)
    assert (canvas[:16] == PAD_VALUE).all()
    assert (canvas[16:48] == 50).all()
    assert (canvas[48:] == PAD_VALUE).all()


def test_box_roundtrip_and_clipping() -> None:
    _, t = letterbox(np.zeros((100, 200, 3), dtype=np.uint8), 64)
    assert box_to_source(0, 16, 64, 48, t) == BoundingBox(0.0, 0.0, 200.0, 100.0)
    assert box_to_source(0, 0, 64, 10, t) is None
    assert box_to_source(-10, 16, 32, 48, t) == BoundingBox(0.0, 0.0, 100.0, 100.0)


def test_to_model_input_rgb_chw() -> None:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[..., 0] = 255                      # azul en BGR
    tensor = to_model_input(image)
    assert tensor.shape == (1, 3, 4, 4)
    assert tensor.dtype == np.float32
    assert tensor.flags["C_CONTIGUOUS"]
    assert tensor[0, 2].max() == pytest.approx(1.0)
    assert tensor[0, 0].max() == 0.0


def test_invalid_size() -> None:
    with pytest.raises(InferenceError):
        letterbox(np.zeros((4, 4, 3), dtype=np.uint8), 0)
```
```python
# tests/integration/test_onnx_session.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.inference.onnx_session import create_session, providers_for
from lector_placas.domain.errors import ModelLoadError
from tests.fixtures.synthetic_onnx import constant_output_model

pytestmark = pytest.mark.integration


def test_providers_for() -> None:
    assert providers_for("cpu") == ["CPUExecutionProvider"]
    assert providers_for("cuda") == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_cpu_session_runs_synthetic_model(tmp_path: Path) -> None:
    expected = np.arange(12, dtype=np.float32).reshape(1, 2, 6)
    session = create_session(constant_output_model(tmp_path / "m.onnx", expected), "cpu")
    outputs = session.run(None, {"images": np.zeros((1, 3, 64, 64), dtype=np.float32)})
    np.testing.assert_array_equal(outputs[0], expected)


def test_invalid_model_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"no es onnx")
    with pytest.raises(ModelLoadError):
        create_session(bad, "cpu")


@pytest.mark.gpu
def test_cuda_session(tmp_path: Path) -> None:
    expected = np.ones((1, 1, 6), dtype=np.float32)
    session = create_session(constant_output_model(tmp_path / "m.onnx", expected), "cuda")
    outputs = session.run(None, {"images": np.zeros((1, 3, 64, 64), dtype=np.float32)})
    np.testing.assert_array_equal(outputs[0], expected)
```

## Fuera de alcance
Decodificación de la salida YOLO (spec 012).

## Definition of Done
- [ ] `uv run pytest tests/unit -m "not gpu"` y `uv run pytest -m integration tests/integration/test_onnx_session.py` en verde.
- [ ] `uv run pytest -m gpu tests/integration/test_onnx_session.py` en verde en la RTX 5050.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
