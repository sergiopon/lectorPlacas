# 012 - Adaptador: modelo YOLO end2end en ONNX

## Objetivo
Ejecutar un modelo YOLO exportado con cabeza end2end (salida `[1, N, 6]`) y convertir su salida en
detecciones en coordenadas de la imagen original.

## Depende de
011.

## Archivos rectores aplicables
- ADR-001 (formato de salida `x1, y1, x2, y2, score, class_id` en píxeles de la entrada letterbox), ADR-009.
- ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/yolo_end2end.py`
- `tests/unit/adapters/test_yolo_end2end.py`

## Dependencias externas
numpy==2.5.3; dev: onnx==1.23.0 (tests).

## Interfaces y tipos involucrados
```python
# de adapters/inference/onnx_session.py (spec 011)
ORT_ERRORS: Final[tuple[type[BaseException], ...]]
class InferenceSessionLike(Protocol):
    def run(self, output_names: list[str] | None,
            input_feed: dict[str, npt.NDArray[Any]]) -> list[npt.NDArray[Any]]: ...
def create_session(model_path: Path, execution_provider: Literal["cuda", "cpu"]) -> InferenceSessionLike: ...
# de adapters/inference/letterbox.py (spec 011)
@dataclass(frozen=True, slots=True)
class LetterboxTransform: scale: float; pad_x: int; pad_y: int; source_width: int; source_height: int
def letterbox(image: ImageBGR, size: int) -> tuple[ImageBGR, LetterboxTransform]: ...
def to_model_input(letterboxed: ImageBGR) -> npt.NDArray[np.float32]: ...
def box_to_source(x1: float, y1: float, x2: float, y2: float, transform: LetterboxTransform) -> BoundingBox | None: ...
# de domain
class BoundingBox: ...
class InferenceError(LectorPlacasError): ...
```
```python
# adapters/inference/yolo_end2end.py — a implementar
INPUT_NAME: Final[str] = "images"

@dataclass(frozen=True, slots=True)
class RawDetection:
    box: BoundingBox
    score: float
    class_id: int

def decode_end2end(output: npt.NDArray[Any], transform: LetterboxTransform,
                   score_threshold: float) -> list[RawDetection]: ...

class YoloEnd2EndOnnxModel:
    def __init__(self, session: InferenceSessionLike, input_size: int) -> None: ...
    def predict(self, image: ImageBGR, score_threshold: float) -> list[RawDetection]: ...
```

## Comportamiento esperado
1. `decode_end2end(output, t, thr)`:
   - `output.ndim != 3` o `output.shape[0] != 1` o `output.shape[2] != 6` → `InferenceError("salida YOLO inesperada: <shape>")`.
   - Para cada fila `(x1, y1, x2, y2, score, cls)`: se omite si `score` no es finito o `score < thr`;
     `box = box_to_source(x1, y1, x2, y2, t)`; se omite si `None`; `class_id = int(round(cls))`;
     `score` se limita a [0, 1].
   - Devuelve la lista ordenada por `score` descendente (orden estable).
2. `YoloEnd2EndOnnxModel.predict(image, thr)`: `letterbox(image, input_size)` → `to_model_input` →
   `session.run(None, {INPUT_NAME: tensor})` (errores `ORT_ERRORS` → `InferenceError("fallo de inferencia YOLO") from e`)
   → `decode_end2end(outputs[0], transform, thr)`.
3. `__init__` valida `input_size` múltiplo de 32 y > 0; si no → `InferenceError`.

## Casos borde y manejo de errores
- Salida con `N = 0` filas → lista vacía.

## Tests de aceptación
```python
# tests/unit/adapters/test_yolo_end2end.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.inference.letterbox import letterbox
from lector_placas.adapters.inference.onnx_session import create_session
from lector_placas.adapters.inference.yolo_end2end import (
    RawDetection, YoloEnd2EndOnnxModel, decode_end2end,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import InferenceError
from tests.fixtures.synthetic_onnx import constant_output_model

ROWS = np.array([[
    [0, 16, 64, 48, 0.9, 2],
    [10, 20, 20, 30, 0.1, 3],
    [0, 0, 64, 10, 0.8, 7],
    [0, 16, 32, 48, 0.95, 3],
]], dtype=np.float32)


def transform():  # type: ignore[no-untyped-def]
    return letterbox(np.zeros((100, 200, 3), dtype=np.uint8), 64)[1]


def test_decode_filters_and_sorts() -> None:
    result = decode_end2end(ROWS, transform(), 0.25)
    assert result == [
        RawDetection(BoundingBox(0.0, 0.0, 100.0, 100.0), pytest.approx(0.95), 3),  # type: ignore[arg-type]
        RawDetection(BoundingBox(0.0, 0.0, 200.0, 100.0), pytest.approx(0.9), 2),  # type: ignore[arg-type]
    ]


def test_decode_rejects_bad_shape() -> None:
    with pytest.raises(InferenceError):
        decode_end2end(np.zeros((1, 3, 5), dtype=np.float32), transform(), 0.25)


def test_decode_empty() -> None:
    assert decode_end2end(np.zeros((1, 0, 6), dtype=np.float32), transform(), 0.25) == []


@pytest.mark.integration
def test_predict_with_synthetic_model(tmp_path: Path) -> None:
    session = create_session(constant_output_model(tmp_path / "m.onnx", ROWS), "cpu")
    model = YoloEnd2EndOnnxModel(session, 64)
    detections = model.predict(np.zeros((100, 200, 3), dtype=np.uint8), 0.5)
    assert [d.class_id for d in detections] == [3, 2]


def test_invalid_input_size() -> None:
    class Dummy:
        def run(self, output_names, input_feed):  # type: ignore[no-untyped-def]
            return []
    with pytest.raises(InferenceError):
        YoloEnd2EndOnnxModel(Dummy(), 100)
```

## Fuera de alcance
Mapeo de clases a vehículos/placas (specs 013 y 015).

## Definition of Done
- [ ] `uv run pytest tests/unit/adapters/test_yolo_end2end.py` (incluye `-m integration`) en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
