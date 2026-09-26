# 033 - Entrenamiento: generador de placas colombianas sintéticas

## Objetivo
Generar recortes sintéticos de placas colombianas (carro amarillo/blanco, moto, motocarro) con su texto,
en el formato CSV de fast-plate-ocr, para complementar el fine-tuning del OCR (≤ 50 % del train).

## Depende de
032 (proyecto `training/ocr`, que ya fija pillow==12.3.0 y opencv-python==4.14.0.94).

## Archivos rectores aplicables
- docs/00-requisitos.md §6 (catálogo y dimensiones verificadas), docs/04-evaluacion.md §5.3 (sintéticos ≤ 50 % del train).
- reglas-seguridad.md SEG-10 (datos sintéticos), SEG-11 (`datasets/` ignorado).

## Archivos a crear/modificar
- `training/ocr/ocr_training/synthetic_plates.py`
- `training/ocr/tests/test_synthetic_plates.py`

## Dependencias externas
pillow==12.3.0, opencv-python==4.14.0.94, numpy (ya en el entorno de la spec 032).

## Interfaces y tipos involucrados
Hechos verificados que usa el generador (docs/00-requisitos.md §6):
- Carro: placa 330×160 mm, una fila de caracteres + nombre del municipio debajo; particular amarillo, público blanco; caracteres negros.
- Moto: placa 235×105 mm, caracteres de 54 mm de alto, una fila + "COLOMBIA" (10,5 mm) debajo; amarilla.
- Motocarro: 235×105 mm, una fila `DDDLLL` + "COLOMBIA"; amarillo (particular) o blanco (público).
NO VERIFICADO (se declara como aproximación en el código): tipografía oficial, alto de caracteres de la placa de carro estándar
(se usa 80 mm, medida verificada solo para la placa antigua/clásica), valores RGB exactos de los colores (Pantone 124 C no convertido).
```python
# de ocr_training/common.py (spec 032)
DATASETS_DIR: Final[Path]
class TrainingError(Exception): ...
```
```python
# ocr_training/synthetic_plates.py — a implementar
DEFAULT_FONT: Final[Path] = Path("/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf")  # OFL-1.1, Fedora
LETTERS: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS: Final[str] = "0123456789"
YELLOW_BGR: Final[tuple[int, int, int]] = (0, 200, 255)     # aproximación visual, no valor oficial
WHITE_BGR: Final[tuple[int, int, int]] = (245, 245, 245)    # aproximación visual
MUNICIPALITIES: Final[tuple[str, ...]] = ("BOGOTA D.C.", "MEDELLIN", "CALI", "BARRANQUILLA", "BUCARAMANGA")

@dataclass(frozen=True, slots=True)
class PlateStyle:
    name: str                     # "car_yellow" | "car_white" | "moto" | "motocarro_yellow" | "motocarro_white"
    pattern: str                  # LLLDDD | LLLDDL | DDDLLL
    size_mm: tuple[int, int]      # (ancho, alto)
    char_height_mm: float
    bottom_text: str | None       # None => municipio aleatorio; "COLOMBIA" para moto/motocarro
    bottom_height_mm: float
    background_bgr: tuple[int, int, int]

STYLES: Final[tuple[PlateStyle, ...]] = (
    PlateStyle("car_yellow", "LLLDDD", (330, 160), 80.0, None, 22.0, YELLOW_BGR),
    PlateStyle("car_white", "LLLDDD", (330, 160), 80.0, None, 22.0, WHITE_BGR),
    PlateStyle("moto", "LLLDDL", (235, 105), 54.0, "COLOMBIA", 10.5, YELLOW_BGR),
    PlateStyle("motocarro_yellow", "DDDLLL", (235, 105), 54.0, "COLOMBIA", 10.5, YELLOW_BGR),
    PlateStyle("motocarro_white", "DDDLLL", (235, 105), 54.0, "COLOMBIA", 10.5, WHITE_BGR),
)

def random_text(pattern: str, rng: random.Random) -> str: ...
def render_plate(text: str, style: PlateStyle, font_path: Path, px_per_mm: float,
                 rng: random.Random) -> npt.NDArray[np.uint8]: ...
def augment(image: npt.NDArray[np.uint8], rng: random.Random) -> npt.NDArray[np.uint8]: ...
def generate_dataset(output_dir: Path, count: int, val_fraction: float, seed: int, font_path: Path) -> tuple[int, int]: ...
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

## Comportamiento esperado
1. `random_text(pattern, rng)`: por posición, `rng.choice(LETTERS)` si `L`, `rng.choice(DIGITS)` si `D`.
2. `render_plate(text, style, font_path, px_per_mm, rng)`:
   - Lienzo Pillow RGB de `round(ancho_mm*px_per_mm) × round(alto_mm*px_per_mm)` con el color de fondo (convertido de BGR a RGB)
     y un borde negro de `max(1, round(2*px_per_mm))` px.
   - Texto principal: `ImageFont.truetype(str(font_path), tamaño)`; el tamaño se busca decreciendo desde `round(char_height_mm*px_per_mm)`
     hasta que el ancho de `draw.textbbox((0, 0), text, font=font)` sea ≤ 90 % del ancho de la placa; centrado horizontalmente,
     en la franja superior `[0, alto - bottom_height_mm*px_per_mm)`, color negro.
   - Texto inferior: `style.bottom_text` o `rng.choice(MUNICIPALITIES)` si es `None`; misma búsqueda con altura `bottom_height_mm*px_per_mm`
     y ancho ≤ 80 %; centrado en la franja inferior.
   - Devuelve el arreglo BGR `uint8` (`np.asarray(img)[:, :, ::-1]` contiguo).
   - `font_path` inexistente o `OSError` de Pillow → `TrainingError("fuente no disponible: <nombre>")`.
3. `augment(image, rng)`: en este orden, con `rng`: rotación uniforme en [-5°, 5°] (`cv2.getRotationMatrix2D`, `cv2.warpAffine`,
   `borderMode=cv2.BORDER_REPLICATE`); con probabilidad 0,5 desenfoque gaussiano de kernel impar 3 o 5; brillo/contraste
   `alpha ∈ [0.7, 1.3]`, `beta ∈ [-30, 30]` con `cv2.convertScaleAbs`; ruido gaussiano σ ∈ [0, 8] recortado a [0, 255].
   Conserva forma y `dtype uint8`.
4. `generate_dataset(output_dir, count, val_fraction, seed, font_path)`:
   - `output_dir` debe estar dentro de `DATASETS_DIR.resolve()` y no existir (si no → `TrainingError`); `count >= 1`;
     `0 <= val_fraction < 1`.
   - `rng = random.Random(seed)`; para `i` en `range(count)`: estilo `STYLES[i % len(STYLES)]`, texto `random_text`,
     `px_per_mm = rng.uniform(0.25, 0.6)`, imagen `augment(render_plate(...))`.
   - Los primeros `round(count * val_fraction)` índices van a `val`, el resto a `train`.
   - Escribe `output_dir/<split>/images/syn_<i:06d>.png` y `output_dir/<split>/annotations.csv` (`image_path,plate_text`,
     rutas `images/syn_<i:06d>.png`). Devuelve `(train_count, val_count)`.
5. CLI: `--output` (relativo a `DATASETS_DIR`, obligatorio), `--count` (int, obligatorio), `--val-fraction` (float, 0.1),
   `--seed` (int, 0), `--font` (Path, `DEFAULT_FONT`). `main` llama `generate_dataset` e imprime los conteos (los textos son
   sintéticos, pero no se imprimen). `if __name__ == "__main__": raise SystemExit(main())`.

## Casos borde y manejo de errores
- Mismo `seed` ⇒ mismos textos e imágenes idénticas (determinismo).
- Los textos generados siempre cumplen el patrón del estilo, y por lo tanto el catálogo de formatos (docs/03-modelo-datos.md §4).

## Tests de aceptación
```python
# training/ocr/tests/test_synthetic_plates.py
from __future__ import annotations

import csv
import random
import re
from pathlib import Path

import numpy as np
import pytest

from ocr_training import synthetic_plates as sp
from ocr_training.common import TrainingError

pytestmark = pytest.mark.skipif(not sp.DEFAULT_FONT.exists(), reason="fuente Liberation Sans no instalada")
PATTERNS = {"LLLDDD": r"^[A-Z]{3}[0-9]{3}$", "LLLDDL": r"^[A-Z]{3}[0-9]{2}[A-Z]$", "DDDLLL": r"^[0-9]{3}[A-Z]{3}$"}


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_random_text_follows_pattern(pattern: str) -> None:
    rng = random.Random(0)
    for _ in range(50):
        assert re.fullmatch(PATTERNS[pattern], sp.random_text(pattern, rng))


@pytest.mark.parametrize("style", sp.STYLES, ids=lambda s: s.name)
def test_render_sizes(style: sp.PlateStyle) -> None:
    image = sp.render_plate("ABC123", style, sp.DEFAULT_FONT, 0.5, random.Random(1))
    assert image.shape == (round(style.size_mm[1] * 0.5), round(style.size_mm[0] * 0.5), 3)
    assert image.dtype == np.uint8
    assert image.min() < 60                       # hay texto oscuro sobre el fondo


def test_augment_keeps_shape() -> None:
    image = np.full((50, 110, 3), 200, np.uint8)
    out = sp.augment(image, random.Random(2))
    assert out.shape == image.shape and out.dtype == np.uint8


def test_missing_font() -> None:
    with pytest.raises(TrainingError):
        sp.render_plate("ABC123", sp.STYLES[0], Path("/no/existe.ttf"), 0.5, random.Random(0))


def test_generate_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    train, val = sp.generate_dataset(tmp_path / "syn", 10, 0.2, 7, sp.DEFAULT_FONT)
    assert (train, val) == (8, 2)
    rows = list(csv.DictReader((tmp_path / "syn" / "train" / "annotations.csv").open(encoding="utf-8")))
    assert len(rows) == 8
    assert all((tmp_path / "syn" / "train" / r["image_path"]).exists() for r in rows)
    assert all(re.fullmatch(r"^[A-Z0-9]{6}$", r["plate_text"]) for r in rows)
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path / "syn", 10, 0.2, 7, sp.DEFAULT_FONT)
    with pytest.raises(TrainingError):
        sp.generate_dataset(tmp_path.parent / "fuera", 10, 0.2, 7, sp.DEFAULT_FONT)


def test_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "DATASETS_DIR", tmp_path)
    sp.generate_dataset(tmp_path / "a", 3, 0.0, 5, sp.DEFAULT_FONT)
    sp.generate_dataset(tmp_path / "b", 3, 0.0, 5, sp.DEFAULT_FONT)
    first = (tmp_path / "a" / "train" / "annotations.csv").read_text(encoding="utf-8")
    assert first == (tmp_path / "b" / "train" / "annotations.csv").read_text(encoding="utf-8")
    assert (tmp_path / "a" / "train" / "images" / "syn_000000.png").read_bytes() == \
        (tmp_path / "b" / "train" / "images" / "syn_000000.png").read_bytes()
```
Nota normativa: `generate_dataset` usa la variable de módulo `DATASETS_DIR` importada de `common` (los tests la sustituyen con `monkeypatch`).

## Fuera de alcance
Mezclar sintéticos con datos reales (se hace al preparar los CSV de entrenamiento: concatenar anotaciones respetando ≤ 50 %);
placas diplomáticas, antiguas y remolques (formatos poco frecuentes o no verificados).

## Definition of Done
- [ ] En `training/ocr`: `uv run pytest tests/test_synthetic_plates.py` en verde.
- [ ] `uv run python -m ocr_training.synthetic_plates --output syn1 --count 1000` genera 900 train + 100 val.
- [ ] Inspección visual de 10 imágenes al azar (operador): texto legible, colores y proporciones plausibles.
