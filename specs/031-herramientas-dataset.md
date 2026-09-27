# 031 - Datasets: unión de datasets de detección y conversión de caracteres a OCR

## Objetivo
Implementar `lector_placas.datasets` y los comandos `lector dataset merge-detection` y
`lector dataset chars-to-ocr`, que preparan (offline) los datos públicos descargados para entrenar el
detector de placas (spec 030) y el OCR (spec 032).

## Depende de
002 (catálogo), 007, 023 (`crop_image`), 028.

## Archivos rectores aplicables
- docs/04-evaluacion.md §5.1 (fuentes y licencias), §5.4 (etiquetado, dHash ≤ 4, partición).
- ARQUITECTURA.md §2 (capa Datasets: no importa `cli` ni `evaluation`), §6.
- reglas-seguridad.md SEG-09/10 (datos reales solo locales; tests sintéticos), SEG-11 (`training/**/datasets/` ignorado), SEG-13, SEG-14.

## Archivos a crear/modificar
- `src/lector_placas/datasets/dhash.py`
- `src/lector_placas/datasets/yolo_format.py`
- `src/lector_placas/datasets/sources.py`
- `src/lector_placas/datasets/merge_detection.py`
- `src/lector_placas/datasets/chars_to_ocr.py`
- `src/lector_placas/cli/dataset_commands.py`
- `src/lector_placas/cli/main.py` (modificar: registrar subcomandos `dataset`)
- `training/detector/sources.example.yaml`
- `docs/datasets/ATRIBUCIONES.md`
- `tests/unit/datasets/__init__.py`, `tests/unit/datasets/synthetic.py`, `test_dhash.py`, `test_yolo_format.py`,
  `test_merge_detection.py`, `test_chars_to_ocr.py`
- `tests/unit/cli/test_dataset_commands.py`

## Dependencias externas
Ninguna nueva (opencv, numpy, pydantic, PyYAML, stdlib `csv`, `hashlib`, `shutil`).

## Interfaces y tipos involucrados
```python
# de domain: BoundingBox, PlateFormatCatalog.matching(text) -> tuple[PlateFormat, ...], PLATE_TEXT_REGEX,
#   DatasetError(LectorPlacasError)
# de application/image_ops.py (023)
def crop_image(image: ImageBGR, box: BoundingBox) -> ImageBGR: ...
# de infrastructure/paths.py (007)
def resolve_within(base: Path, candidate: Path) -> Path: ...
def ensure_private_dir(path: Path) -> Path: ...
# de infrastructure/config.py (006): AppConfig.root_dir, AppConfig.plate_catalog()
```
Estructura esperada de cada dataset descargado de Roboflow en formato "YOLOv8" (**si la estructura real difiere,
detente y reporta**): `<fuente>/data.yaml` (clave `names`: lista o dict id→nombre) y carpetas `train/`, `valid/`, `test/`
(las que existan), cada una con `images/` y `labels/`; etiqueta `labels/<stem>.txt` con líneas `clase cx cy w h` normalizadas.
```python
# datasets/dhash.py
def dhash(image: ImageBGR) -> int: ...
def hamming(a: int, b: int) -> int: ...

# datasets/yolo_format.py
@dataclass(frozen=True, slots=True)
class YoloBox:
    class_id: int      # >= 0
    cx: float          # [0, 1]
    cy: float          # [0, 1]
    w: float           # (0, 1]
    h: float           # (0, 1]
def parse_label_file(path: Path) -> list[YoloBox]: ...
def format_labels(boxes: Sequence[YoloBox]) -> str: ...
def yolo_to_pixels(box: YoloBox, width: int, height: int) -> BoundingBox | None: ...
def read_class_names(data_yaml: Path) -> dict[int, str]: ...

# datasets/sources.py
PLACEHOLDER: Final[str] = "COMPLETAR"
class DatasetSource(BaseModel):           # extra="forbid", frozen=True
    name: str                             # ^[a-z0-9_-]{1,40}$
    path: Path                            # relativa, sin ".."
    url: str                              # empieza por "https://"
    license: str                          # no vacío
    plate_classes: tuple[str, ...]        # >= 1, sin PLACEHOLDER
class SourcesFile(BaseModel):             # extra="forbid", frozen=True
    version: Literal[1]
    sources: tuple[DatasetSource, ...]    # >= 1, nombres únicos
def load_sources(path: Path) -> SourcesFile: ...

# datasets/merge_detection.py
SPLIT_MAP: Final[Mapping[str, str]] = MappingProxyType({"train": "train", "valid": "val", "test": "val"})
IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
DUPLICATE_DISTANCE: Final[int] = 4
@dataclass(frozen=True, slots=True)
class MergeSummary:
    train_images: int
    val_images: int
    dropped_duplicates: int
    boxes: int
def merge_detection(sources_file: Path, raw_root: Path, output_dir: Path) -> MergeSummary: ...

# datasets/chars_to_ocr.py
PLATE_CLASS: Final[str] = "placa"
IGNORED_CLASSES: Final[frozenset[str]] = frozenset({"ciudad"})
@dataclass(frozen=True, slots=True)
class OcrSummary:
    train_crops: int
    val_crops: int
    skipped: int
    dropped_duplicates: int
def plate_text_from_boxes(plate: BoundingBox, chars: Sequence[tuple[BoundingBox, str]]) -> str: ...
def chars_to_ocr(source_dir: Path, output_dir: Path, catalog: PlateFormatCatalog) -> OcrSummary: ...

# cli/dataset_commands.py
def register_dataset_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...
def cmd_merge_detection(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_chars_to_ocr(args: argparse.Namespace, config: AppConfig) -> int: ...
```

## Comportamiento esperado
1. `dhash(image)`: gris (`cv2.COLOR_BGR2GRAY`), `cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)`, `bits = resized[:, 1:] > resized[:, :-1]`
   (8×8); entero de 64 bits recorriendo `bits.flatten()` de izquierda a derecha como bits de mayor a menor peso. `hamming(a, b) = (a ^ b).bit_count()`.
2. `parse_label_file(path)`: archivo inexistente o vacío → `[]`; cada línea no vacía es una caja de 5 campos (`int float float float float`)
   o un **polígono** (corrección 2026-09-26: Roboflow exporta `yolov8` con polígonos en proyectos con anotación de segmentación):
   `clase x1 y1 x2 y2 ... xn yn` con `n >= 3` (número **impar** de campos, mínimo 7), que se convierte en su caja envolvente:
   `cx = (min(x) + max(x)) / 2`, `w = max(x) - min(x)` (ídem y). El resultado debe cumplir los rangos de `YoloBox`; cualquier otra
   forma (p. ej. 4, 6 u 8 campos, valores no numéricos, o polígono de ancho o alto 0) → `DatasetError(f"etiqueta inválida: {path.name}:{n}")`.
   `format_labels(boxes)`: una línea por caja `f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"`, terminada en `"\n"` si hay cajas; `""` si no.
   `yolo_to_pixels`: `x1 = (cx - w/2) * width`, `x2 = (cx + w/2) * width` (ídem y), limitado a la imagen; vacío → `None`.
   `read_class_names(data_yaml)`: `yaml.safe_load`; `names` lista → `dict(enumerate(...))`; dict → claves `int`; otro → `DatasetError`.
3. `load_sources(path)`: YAML seguro + validación; errores → `DatasetError("fuentes inválidas: <detalle>")`. `plate_classes` con
   `PLACEHOLDER` → error con mensaje `"complete plate_classes de <name> leyendo su data.yaml"`.
4. `merge_detection(sources_file, raw_root, output_dir)`:
   1. `output_dir` existente y no vacío → `DatasetError("el directorio de salida no está vacío")`.
   2. Por fuente (orden del archivo): `src = resolve_within(raw_root, source.path)`; `names = read_class_names(src / "data.yaml")`;
      cada nombre de `plate_classes` debe existir en `names` (si no → `DatasetError`); `plate_ids` = sus ids.
   3. Por split en `("train", "valid", "test")` si existe `src/split/images`: imágenes con sufijo en `IMAGE_SUFFIXES` en orden `sorted`;
      etiqueta `src/split/labels/<stem>.txt`; cajas conservadas = las de `plate_ids`, remapeadas a `class_id = 0`
      (las imágenes sin placas se conservan como negativos); `cv2.imread` `None` → `DatasetError`; se calcula `dhash`.
   4. Primero se escriben todas las entradas `train`; luego cada entrada `val` se descarta si su `dhash` está a distancia
      `<= DUPLICATE_DISTANCE` de alguna entrada `train` o `val` ya aceptada (cuenta en `dropped_duplicates`).
   5. Salida: `images/<split>/<fuente>__<stem><sufijo>` (copia con `shutil.copyfile`), `labels/<split>/<fuente>__<stem>.txt`
      (`format_labels`), `data.yaml` con `{"path": str(output_dir.resolve()), "train": "images/train", "val": "images/val", "names": {0: "plate"}}`
      y `provenance.csv` con cabecera `split,output_name,source,original_path,sha256` (ruta original relativa a `raw_root`,
      SHA-256 del archivo de imagen). Directorios con `ensure_private_dir`.
   6. Devuelve `MergeSummary` (`boxes` = total de cajas escritas).
5. `plate_text_from_boxes(plate, chars)`: conserva los caracteres cuyo centro está dentro de `plate` (bordes incluidos), los ordena
   por centro x y devuelve la concatenación en mayúsculas.
6. `chars_to_ocr(source_dir, output_dir, catalog)`:
   1. Salida no vacía → `DatasetError`. `names = read_class_names(source_dir / "data.yaml")`; cada nombre debe ser `PLATE_CLASS`,
      estar en `IGNORED_CLASSES` o cumplir `^[0-9A-Za-z]$`; si no → `DatasetError(f"clase desconocida: {nombre}")`.
   2. Por split (`SPLIT_MAP`) e imagen: cajas en píxeles con `yolo_to_pixels`; por cada caja `placa` (índice `k` en orden de archivo):
      `text = plate_text_from_boxes(...)`; si `text` no cumple `PLATE_TEXT_REGEX` o `catalog.matching(text)` está vacío → `skipped += 1`;
      si no, `crop = crop_image(image, placa)` y `dhash(crop)`.
   2b. **Fuente sin `valid` ni `test`** (corrección 2026-09-27; el export de Roboflow del OCR solo trae `train`): si ninguno de los
      splits de `SPLIT_MAP` que mapean a `val` existe en `source_dir`, los recortes de `train` se reparten por **grupo de imagen de
      origen**: `grupo = re.sub(r"\.rf\.[0-9a-fA-F]+$", "", image_path.stem)` (Roboflow añade `.rf.<hash>` a cada copia de la misma
      imagen). El recorte va a `val` si `int(hashlib.sha256(grupo.encode("utf-8")).hexdigest(), 16) % 10 == 0` y a `train` si no; así
      ninguna copia del mismo origen queda repartida entre train y val. Si la fuente sí trae `valid` o `test`, no se aplica y se respeta
      su partición.
   3. Deduplicación igual que en el paso 4.4 (val contra train y contra val aceptado). En el caso 2b se descartan además de val,
      sumándolos a `dropped_duplicates`, los recortes cuyo `text` aparece en algún recorte de train (el mismo vehículo con otro nombre).
   4. Escribe `output_dir/<split>/images/<fuente>__<stem>_<k>.png` (`cv2.imwrite`) y `output_dir/<split>/annotations.csv` con cabecera
      `image_path,plate_text` y rutas `images/<nombre>` (formato de fast-plate-ocr). `fuente = source_dir.name`.
   5. Devuelve `OcrSummary`.
7. CLI (`register_dataset_commands`, llamada desde `main.build_parser`): subcomando `dataset` con
   - `merge-detection --sources PATH --output NOMBRE` → `merge_detection(resolve_within(root/"training/detector", args.sources),
     root/"training/detector/datasets/raw", resolve_within(root/"training/detector/datasets", Path(args.output)))`;
   - `chars-to-ocr --source PATH --output NOMBRE` → `chars_to_ocr(resolve_within(root/"training/ocr/datasets/raw", args.source),
     resolve_within(root/"training/ocr/datasets", Path(args.output)), config.plate_catalog())`;
   ambos `network=False`, escriben solo conteos en stdout (nunca textos de placa) y devuelven 0. `root = config.root_dir`.
8. `training/detector/sources.example.yaml` **literal**:
```yaml
version: 1
sources:
  - name: placas_colombianas
    path: placas_colombianas
    url: https://universe.roboflow.com/licenseplates-gk27i/placas-colombianas
    license: CC BY 4.0
    plate_classes: [COMPLETAR]   # NO VERIFICADO: leer names en data.yaml tras descargar
  - name: usco
    path: usco
    url: https://universe.roboflow.com/usco-thj9e/placas-colombia-ixdpr
    license: MIT (declarada por quien subió el dataset)
    plate_classes: [placa]
  - name: placas_motos_carros
    path: placas_motos_carros
    url: https://universe.roboflow.com/reimerjsuarez/placas_motos_carros
    license: CC BY 4.0
    plate_classes: [Placas]
  - name: motos_placas
    path: motos_placas
    url: https://universe.roboflow.com/placas-sn7fb/motos-placas
    license: CC BY 4.0
    plate_classes: [COMPLETAR]   # clases H, I, Q, motos-placas: NO VERIFICADO cuál es la placa
```
9. `docs/datasets/ATRIBUCIONES.md`: tabla `Dataset | URL | Licencia | Versión descargada | Fecha de descarga | Uso` con las cinco
   fuentes de docs/04-evaluacion.md §5.1 (URL y licencia copiadas de allí; versión y fecha como `COMPLETAR`), y la frase
   "Los datasets CC BY 4.0 exigen atribución; esta tabla se publica con el repositorio."

## Casos borde y manejo de errores
- Nada en consola, logs ni reportes contiene textos de placa (solo conteos).
- Los recortes y copias de imágenes quedan bajo `training/**/datasets/` (gitignored) y nunca se envían a la API externa.

## Tests de aceptación
```python
# tests/unit/datasets/synthetic.py
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml


def noise(seed: int, height: int = 64, width: int = 96) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (height, width, 3), dtype=np.uint8)


def make_source(root: Path, name: str, names: object,
                items: list[tuple[str, str, np.ndarray, list[str]]]) -> Path:
    source = root / name
    source.mkdir(parents=True)
    (source / "data.yaml").write_text(yaml.safe_dump({"names": names}), encoding="utf-8")
    for split, stem, image, lines in items:
        (source / split / "images").mkdir(parents=True, exist_ok=True)
        (source / split / "labels").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(source / split / "images" / f"{stem}.png"), image)
        (source / split / "labels" / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    return source
```
```python
# tests/unit/datasets/test_dhash.py
from __future__ import annotations

from lector_placas.datasets.dhash import dhash, hamming
from tests.unit.datasets.synthetic import noise


def test_dhash_identity_and_difference() -> None:
    assert hamming(dhash(noise(1)), dhash(noise(1))) == 0
    assert hamming(dhash(noise(1)), dhash(noise(2))) > 4
    assert 0 <= dhash(noise(3)) < 2**64
    assert hamming(0b1011, 0b0001) == 2
```
```python
# tests/unit/datasets/test_yolo_format.py
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.yolo_format import (
    YoloBox, format_labels, parse_label_file, read_class_names, yolo_to_pixels,
)
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError


def test_parse_and_format(tmp_path: Path) -> None:
    label = tmp_path / "a.txt"
    label.write_text("1 0.5 0.5 0.2 0.1\n\n0 0.25 0.25 0.5 0.5\n", encoding="utf-8")
    boxes = parse_label_file(label)
    assert boxes == [YoloBox(1, 0.5, 0.5, 0.2, 0.1), YoloBox(0, 0.25, 0.25, 0.5, 0.5)]
    assert format_labels(boxes[:1]) == "1 0.500000 0.500000 0.200000 0.100000\n"
    assert format_labels([]) == ""
    assert parse_label_file(tmp_path / "missing.txt") == []


@pytest.mark.parametrize(
    "line",
    [
        "1 0.5 0.5 0.2",
        "x 0.5 0.5 0.2 0.1",
        "1 1.5 0.5 0.2 0.1",
        "1 0.5 0.5 0 0.1",
        "1 0.5 0.5 0.2 0.1 0.3",
        "1 0.2 0.2 0.6 0.2 0.2 0.2",
    ],
)
def test_invalid_lines(tmp_path: Path, line: str) -> None:
    label = tmp_path / "b.txt"
    label.write_text(line, encoding="utf-8")
    with pytest.raises(DatasetError):
        parse_label_file(label)


def test_polygon_becomes_bounding_box(tmp_path: Path) -> None:
    label = tmp_path / "p.txt"
    label.write_text("3 0.2 0.2 0.6 0.2 0.6 0.4 0.2 0.4\n1 0.5 0.5 0.2 0.1", encoding="utf-8")
    polygon, box = parse_label_file(label)
    assert polygon.class_id == 3
    assert (polygon.cx, polygon.cy, polygon.w, polygon.h) == pytest.approx((0.4, 0.3, 0.4, 0.2))
    assert box == YoloBox(1, 0.5, 0.5, 0.2, 0.1)


def test_pixels_and_names(tmp_path: Path) -> None:
    assert yolo_to_pixels(YoloBox(0, 0.5, 0.5, 0.5, 0.5), 200, 100) == BoundingBox(50.0, 25.0, 150.0, 75.0)
    data = tmp_path / "data.yaml"
    data.write_text(yaml.safe_dump({"names": ["car", "placa"]}), encoding="utf-8")
    assert read_class_names(data) == {0: "car", 1: "placa"}
    data.write_text(yaml.safe_dump({"names": {0: "Placas"}}), encoding="utf-8")
    assert read_class_names(data) == {0: "Placas"}
    data.write_text(yaml.safe_dump({"names": "x"}), encoding="utf-8")
    with pytest.raises(DatasetError):
        read_class_names(data)
```
```python
# tests/unit/datasets/test_merge_detection.py
from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.merge_detection import merge_detection
from lector_placas.datasets.sources import load_sources
from lector_placas.domain.errors import DatasetError
from tests.unit.datasets.synthetic import make_source, noise


def sources_file(tmp_path: Path, alfa_classes: list[str]) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "sources": [
        {"name": "alfa", "path": "alfa", "url": "https://example.org/alfa", "license": "CC BY 4.0",
         "plate_classes": alfa_classes},
        {"name": "beta", "path": "beta", "url": "https://example.org/beta", "license": "MIT",
         "plate_classes": ["Placas"]},
    ]}), encoding="utf-8")
    return path


def build_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    make_source(raw, "alfa", ["car", "placa"], [
        ("train", "a1", noise(1), ["1 0.5 0.5 0.2 0.1", "0 0.3 0.3 0.2 0.2"]),
        ("train", "a2", noise(2), ["0 0.5 0.5 0.4 0.4"]),
        ("valid", "a3", noise(1), ["1 0.5 0.5 0.2 0.1"]),
        ("test", "a4", noise(4), ["1 0.5 0.5 0.1 0.1"]),
    ])
    make_source(raw, "beta", {0: "Placas"}, [("train", "b1", noise(5), ["0 0.5 0.5 0.3 0.1"])])
    return raw


def test_merge_detection(tmp_path: Path) -> None:
    out = tmp_path / "merged"
    summary = merge_detection(sources_file(tmp_path, ["placa"]), build_raw(tmp_path), out)
    assert (summary.train_images, summary.val_images, summary.dropped_duplicates, summary.boxes) == (3, 1, 1, 3)
    assert (out / "labels" / "train" / "alfa__a1.txt").read_text() == "0 0.500000 0.500000 0.200000 0.100000\n"
    assert (out / "labels" / "train" / "alfa__a2.txt").read_text() == ""
    assert (out / "images" / "val" / "alfa__a4.png").exists()
    assert not (out / "images" / "val" / "alfa__a3.png").exists()
    data = yaml.safe_load((out / "data.yaml").read_text())
    assert data["names"] == {0: "plate"} and data["val"] == "images/val"
    rows = list(csv.DictReader((out / "provenance.csv").open(encoding="utf-8")))
    assert len(rows) == 4 and {r["source"] for r in rows} == {"alfa", "beta"}


def test_merge_errors(tmp_path: Path) -> None:
    raw = build_raw(tmp_path)
    with pytest.raises(DatasetError):
        merge_detection(sources_file(tmp_path, ["plate"]), raw, tmp_path / "o1")
    out = tmp_path / "o2"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(DatasetError):
        merge_detection(sources_file(tmp_path, ["placa"]), raw, out)


def test_placeholder_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatasetError):
        load_sources(sources_file(tmp_path, ["COMPLETAR"]))
```
```python
# tests/unit/datasets/test_chars_to_ocr.py
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from lector_placas.datasets.chars_to_ocr import chars_to_ocr, plate_text_from_boxes
from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError
from tests.fixtures.plate_catalog import build_test_catalog
from tests.unit.datasets.synthetic import make_source, noise

NAMES = ["A", "B", "c", "1", "2", "3", "placa", "ciudad"]
PLATE = "6 0.5 0.5 0.8 0.6"
CHARS = ["3 0.55 0.45 0.08 0.3", "0 0.20 0.45 0.08 0.3", "5 0.75 0.45 0.08 0.3",
         "2 0.40 0.45 0.08 0.3", "1 0.30 0.45 0.08 0.3", "4 0.65 0.45 0.08 0.3",
         "7 0.50 0.72 0.60 0.08"]


def test_plate_text_from_boxes() -> None:
    plate = BoundingBox(0, 0, 100, 40)
    chars = [(BoundingBox(50, 5, 60, 30), "2"), (BoundingBox(10, 5, 20, 30), "a"),
             (BoundingBox(150, 5, 160, 30), "Z")]
    assert plate_text_from_boxes(plate, chars) == "A2"


def test_chars_to_ocr(tmp_path: Path) -> None:
    source = make_source(tmp_path / "raw", "fuente", NAMES, [
        ("train", "img1", noise(1, 100, 200), [PLATE, *CHARS]),
        ("train", "img2", noise(2, 100, 200), [PLATE, CHARS[1], CHARS[4], CHARS[3]]),
        ("valid", "img3", noise(1, 100, 200), [PLATE, *CHARS]),
    ])
    out = tmp_path / "ocr"
    summary = chars_to_ocr(source, out, build_test_catalog())
    assert (summary.train_crops, summary.val_crops, summary.skipped, summary.dropped_duplicates) == (1, 0, 1, 1)
    rows = list(csv.DictReader((out / "train" / "annotations.csv").open(encoding="utf-8")))
    assert rows == [{"image_path": "images/fuente__img1_0.png", "plate_text": "ABC123"}]
    assert (out / "train" / "images" / "fuente__img1_0.png").exists()


def test_unknown_class(tmp_path: Path) -> None:
    source = make_source(tmp_path / "raw", "fuente", ["placa", "persona"], [])
    with pytest.raises(DatasetError):
        chars_to_ocr(source, tmp_path / "ocr", build_test_catalog())


ALT_CHARS = [
    "5 0.55 0.45 0.08 0.3",
    "0 0.20 0.45 0.08 0.3",
    "3 0.75 0.45 0.08 0.3",
    "2 0.40 0.45 0.08 0.3",
    "1 0.30 0.45 0.08 0.3",
    "4 0.65 0.45 0.08 0.3",
]


def test_train_only_source_is_split_by_group(tmp_path: Path) -> None:
    # sha256(grupo) % 10: gA -> 0 (val); gB -> 3 y gD -> 5 (train)
    source = make_source(
        tmp_path / "raw",
        "fuente",
        NAMES,
        [
            ("train", "gA.rf.a1", noise(1, 100, 200), [PLATE, *ALT_CHARS]),
            ("train", "gA.rf.b2", noise(2, 100, 200), [PLATE, *ALT_CHARS]),
            ("train", "gB.rf.c3", noise(3, 100, 200), [PLATE, *CHARS]),
            ("train", "gD.rf.d4", noise(4, 100, 200), [PLATE, *CHARS]),
        ],
    )
    out = tmp_path / "ocr"
    summary = chars_to_ocr(source, out, build_test_catalog())
    assert (summary.train_crops, summary.val_crops, summary.skipped, summary.dropped_duplicates) == (2, 2, 0, 0)
    val_rows = list(csv.DictReader((out / "val" / "annotations.csv").open(encoding="utf-8")))
    assert sorted(row["image_path"] for row in val_rows) == [
        "images/fuente__gA.rf.a1_0.png",
        "images/fuente__gA.rf.b2_0.png",
    ]
    assert {row["plate_text"] for row in val_rows} == {"ABC321"}


def test_group_split_drops_val_text_already_in_train(tmp_path: Path) -> None:
    source = make_source(
        tmp_path / "raw",
        "fuente",
        NAMES,
        [
            ("train", "gA.rf.a1", noise(1, 100, 200), [PLATE, *CHARS]),
            ("train", "gB.rf.c3", noise(3, 100, 200), [PLATE, *CHARS]),
        ],
    )
    summary = chars_to_ocr(source, tmp_path / "ocr", build_test_catalog())
    assert (summary.train_crops, summary.val_crops, summary.skipped, summary.dropped_duplicates) == (1, 0, 0, 1)
```
```python
# tests/unit/cli/test_dataset_commands.py
from __future__ import annotations

from pathlib import Path

from lector_placas.cli.main import build_parser


def test_dataset_subcommands() -> None:
    parser = build_parser()
    merge = parser.parse_args(["dataset", "merge-detection", "--sources", "s.yaml", "--output", "merged"])
    assert (merge.sources, merge.output, merge.network) == (Path("s.yaml"), "merged", False)
    chars = parser.parse_args(["dataset", "chars-to-ocr", "--source", "raw/x", "--output", "ocr1"])
    assert (chars.source, chars.output) == (Path("raw/x"), "ocr1")
```

## Fuera de alcance
Descargar los datasets (manual desde el navegador, docs/04-evaluacion.md §5.1); anotar frames propios (Label Studio);
exportar recortes propios de la BD (**decisión pendiente del usuario**, docs/04-evaluacion.md §5.2).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde (incluye la capa `datasets` en el test de dependencias).
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `training/detector/sources.example.yaml` y `docs/datasets/ATRIBUCIONES.md` creados.
