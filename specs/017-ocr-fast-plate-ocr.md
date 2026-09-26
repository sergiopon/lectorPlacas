# 017 - Adaptador: lector OCR fast-plate-ocr

## Objetivo
Implementar `FastPlateOcrReader` (puerto `PlateReader`) sobre `LicensePlateRecognizer` de
fast-plate-ocr 1.1.0 con modelo y configuración locales.

## Depende de
011.

## Archivos rectores aplicables
- ADR-003 (API y configuración verificadas). SEG-19 (rutas locales, nunca `hub_ocr_model`).
- ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/inference/plate_reader_fpo.py`
- `tests/unit/adapters/test_plate_reader_fpo.py`

## Dependencias externas
fast-plate-ocr==1.1.0 (ya instalado; usa el `onnxruntime` provisto por onnxruntime-gpu).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class PlateReader(Protocol):
    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]: ...
# de domain
@dataclass(frozen=True, slots=True)
class OcrResult: text: str; char_confidences: tuple[float, ...]   # text ^[A-Z0-9]{0,10}$
class InferenceError(LectorPlacasError): ...
class ModelLoadError(LectorPlacasError): ...
# de adapters/inference/onnx_session.py (spec 011)
ORT_ERRORS: Final[tuple[type[BaseException], ...]]
# API verificada de fast-plate-ocr 1.1.0
# from fast_plate_ocr import LicensePlateRecognizer
# LicensePlateRecognizer(hub_ocr_model=None, device="auto", providers=None, sess_options=None,
#                        onnx_model_path=None, plate_config_path=None, force_download=False)
# .config.image_color_mode -> "rgb" | "grayscale"
# .run(source: list[np.ndarray], return_confidence: bool = False, remove_pad_char: bool = True) -> list[PlatePrediction]
# PlatePrediction(plate: str, char_probs: np.ndarray | None, region: str | None, region_prob: float | None)
#   char_probs tiene longitud max_plate_slots (10), NO la del texto; plate solo quita "_" finales.
```
```python
# adapters/inference/plate_reader_fpo.py — a implementar
PAD_CHAR: Final[str] = "_"

class RecognizerLike(Protocol):
    @property
    def config(self) -> Any: ...
    def run(self, source: list[npt.NDArray[np.uint8]], return_confidence: bool = ...) -> list[Any]: ...

class FastPlateOcrReader:
    def __init__(self, recognizer: RecognizerLike) -> None: ...
    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]: ...

def create_fast_plate_ocr_reader(onnx_model_path: Path, plate_config_path: Path,
                                 providers: list[str]) -> FastPlateOcrReader: ...
```

## Comportamiento esperado
1. `create_fast_plate_ocr_reader`: `LicensePlateRecognizer(onnx_model_path=onnx_model_path, plate_config_path=plate_config_path, providers=providers)`;
   `ORT_ERRORS`, `FileNotFoundError` o `TypeError` → `ModelLoadError("no se pudo cargar el OCR: <onnx_model_path.name>") from e`.
2. `read(plate_images)`: lista vacía → `[]`. Conversión de color según `recognizer.config.image_color_mode`:
   `"rgb"` → `cv2.cvtColor(img, cv2.COLOR_BGR2RGB)`; `"grayscale"` → `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`;
   otro valor → `InferenceError("modo de color no soportado")`.
3. `predictions = recognizer.run(convertidas, return_confidence=True)`; `ORT_ERRORS` → `InferenceError("fallo del OCR") from e`.
   Si `len(predictions) != len(plate_images)` → `InferenceError("el OCR devolvió un número de resultados distinto")`.
4. Por cada predicción: `text = pred.plate` (sin convertir mayúsculas/minúsculas); si `pred.char_probs is None` → `InferenceError`.
   Si `PAD_CHAR in text` o `text` no cumple `^[A-Z0-9]{0,10}$` → `OcrResult("", ())`.
   Si no: `OcrResult(text, tuple(min(1.0, max(0.0, float(p))) for p in pred.char_probs[:len(text)]))`.

## Casos borde y manejo de errores
- Nunca uses `hub_ocr_model` (descargaría de internet).

## Tests de aceptación
```python
# tests/unit/adapters/test_plate_reader_fpo.py
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fast_plate_ocr.core.types import PlatePrediction

from lector_placas.adapters.inference.plate_reader_fpo import (
    FastPlateOcrReader, create_fast_plate_ocr_reader,
)
from lector_placas.domain.entities import OcrResult
from lector_placas.domain.errors import InferenceError, ModelLoadError

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "models" / "fpo-cct-xs-v2-global" / "cct_xs_v2_global.onnx"
CONFIG = ROOT / "models" / "fpo-cct-xs-v2-global-config" / "cct_xs_v2_global_plate_config.yaml"
PROBS = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.99, 0.99, 0.99, 0.99], dtype=np.float32)


class FakeRecognizer:
    def __init__(self, plates: list[str], mode: str = "rgb") -> None:
        self.config = SimpleNamespace(image_color_mode=mode)
        self.plates = plates
        self.received: list[np.ndarray] = []

    def run(self, source: list[np.ndarray], return_confidence: bool = False) -> list[PlatePrediction]:
        assert return_confidence
        self.received = source
        return [PlatePrediction(p, PROBS) for p in self.plates]


def blue(n: int = 1) -> list[np.ndarray]:
    image = np.zeros((20, 60, 3), np.uint8)
    image[..., 0] = 255
    return [image] * n


def test_trims_probabilities_and_converts_to_rgb() -> None:
    fake = FakeRecognizer(["ABC123"])
    result = FastPlateOcrReader(fake).read(blue())
    assert result[0].text == "ABC123"
    assert result[0].char_confidences == pytest.approx((0.9, 0.8, 0.7, 0.6, 0.5, 0.4))
    assert fake.received[0][0, 0].tolist() == [0, 0, 255]


def test_grayscale_mode() -> None:
    fake = FakeRecognizer(["AB1"], mode="grayscale")
    FastPlateOcrReader(fake).read(blue())
    assert fake.received[0].ndim == 2


@pytest.mark.parametrize("plate", ["AB_12", "abc123", "ÑBC123"])
def test_invalid_predictions_become_empty(plate: str) -> None:
    fake = FakeRecognizer([plate])
    assert FastPlateOcrReader(fake).read(blue()) == [OcrResult("", ())]


def test_empty_input_and_count_mismatch() -> None:
    assert FastPlateOcrReader(FakeRecognizer([])).read([]) == []
    with pytest.raises(InferenceError):
        FastPlateOcrReader(FakeRecognizer(["A", "B"])).read(blue(1))


def test_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError):
        create_fast_plate_ocr_reader(tmp_path / "m.onnx", tmp_path / "c.yaml", ["CPUExecutionProvider"])


@pytest.mark.integration
@pytest.mark.skipif(not (MODEL.exists() and CONFIG.exists()), reason="modelo no descargado")
def test_real_model_reads_synthetic_image() -> None:
    reader = create_fast_plate_ocr_reader(MODEL, CONFIG, ["CPUExecutionProvider"])
    result = reader.read(blue())
    assert len(result) == 1
    assert len(result[0].text) == len(result[0].char_confidences)
```
## Fuera de alcance
Fine-tuning (spec 032).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
