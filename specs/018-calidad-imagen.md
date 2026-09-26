# 018 - Adaptador: nitidez de recortes

## Objetivo
Implementar `LaplacianQualityScorer` (puerto `ImageQualityScorer`): varianza del Laplaciano sobre el
recorte en gris normalizado a 128×64.

## Depende de
005.

## Archivos rectores aplicables
- ADR-006 (`min_sharpness`, ranking del mejor recorte). ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/adapters/imaging/quality.py`
- `tests/unit/adapters/test_quality.py`

## Dependencias externas
opencv-python==4.14.0.94 (ya instalado).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class ImageQualityScorer(Protocol):
    def sharpness(self, image: ImageBGR) -> float: ...
```
```python
# adapters/imaging/quality.py — a implementar
NORMALIZED_SIZE: Final[tuple[int, int]] = (128, 64)   # (ancho, alto) para cv2.resize

class LaplacianQualityScorer:
    def sharpness(self, image: ImageBGR) -> float: ...
```

## Comportamiento esperado
1. `gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)`; `resized = cv2.resize(gray, NORMALIZED_SIZE, interpolation=cv2.INTER_AREA)`;
   devuelve `float(cv2.Laplacian(resized, cv2.CV_64F).var())`.
2. Imagen vacía (algún lado 0) → `InferenceError("imagen vacía")`.

## Casos borde y manejo de errores
- El resultado siempre es finito y ≥ 0.

## Tests de aceptación
```python
# tests/unit/adapters/test_quality.py
from __future__ import annotations

import cv2
import numpy as np
import pytest

from lector_placas.adapters.imaging.quality import LaplacianQualityScorer
from lector_placas.domain.errors import InferenceError


def checkerboard() -> np.ndarray:
    tile = np.kron([[0, 255] * 8, [255, 0] * 8] * 4, np.ones((4, 4))).astype(np.uint8)
    return np.dstack([tile] * 3)


def test_flat_image_is_zero() -> None:
    assert LaplacianQualityScorer().sharpness(np.full((30, 90, 3), 128, np.uint8)) == 0.0


def test_sharp_beats_blurred() -> None:
    sharp = checkerboard()
    blurred = cv2.GaussianBlur(sharp, (9, 9), 3)
    scorer = LaplacianQualityScorer()
    assert scorer.sharpness(sharp) > scorer.sharpness(blurred) > 0.0


def test_empty_image_raises() -> None:
    with pytest.raises(InferenceError):
        LaplacianQualityScorer().sharpness(np.zeros((0, 10, 3), np.uint8))
```

## Fuera de alcance
Umbral de filtrado (lo aplica `ProcessVideo`, spec 024).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
