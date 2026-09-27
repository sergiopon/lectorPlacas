# 037 - Métrica del detector de placas sobre un dataset YOLO (`lector evaluate-detector`)

## Objetivo
Medir precisión, recall y F1 del detector de placas configurado sobre el split de validación del dataset unificado
(`training/detector/datasets/merged`, spec 028/036), sin anotar nada a mano, y guardar un reporte JSON comparable.

## Depende de
014, 015, 029, 031.

## Archivos rectores aplicables
- ARQUITECTURA.md: regla de dependencia (`evaluation` y `datasets` no se importan entre sí; la CLI los une).
- reglas-seguridad.md: SEG-13 (`resolve_within`), SEG-20 (sin red), SEG-17 (modelo verificado por el registro).
- docs/04-evaluacion.md §4 (reportes en `data/eval/reports/`, 0600).

## Archivos a crear/modificar
- `src/lector_placas/evaluation/detection_metrics.py` (nuevo)
- `src/lector_placas/datasets/yolo_split.py` (nuevo)
- `src/lector_placas/cli/detector_evaluation_commands.py` (nuevo)
- `src/lector_placas/cli/evaluation_commands.py` (una línea: llamar `register_detector_evaluation(subparsers)` al final de
  `register_evaluation_commands`, más su import)
- `tests/unit/evaluation/test_detection_metrics.py` (nuevo)
- `tests/unit/datasets/test_yolo_split.py` (nuevo)
- `tests/unit/cli/test_detector_evaluation_cli.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
```python
# existentes
@dataclass(frozen=True, slots=True)
class BoundingBox: x1: float; y1: float; x2: float; y2: float   # propiedades width, height
@dataclass(frozen=True, slots=True)
class PlateDetection: box: BoundingBox; confidence: float
class PlateDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...
def parse_label_file(path: Path) -> list[YoloBox]: ...                              # datasets/yolo_format.py
def yolo_to_pixels(box: YoloBox, width: int, height: int) -> BoundingBox | None: ... # datasets/yolo_format.py
def write_report(reports_dir: Path, payload: Mapping[str, object], created_at: datetime) -> Path: ...
# cli/composition.py: build_registry(config), build_plate_detector(config, registry)
# cli/evaluation_commands.py: _reports_dir(config) -> Path, _format_metric(value: float | None) -> str
```
```python
# evaluation/detection_metrics.py — nuevo (solo stdlib + domain)
IOU_THRESHOLD: Final[float] = 0.5

@dataclass(frozen=True, slots=True)
class DetectionCounts:
    true_positives: int
    false_positives: int
    false_negatives: int

@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    images: int
    counts: DetectionCounts
    precision: float | None     # TP / (TP + FP); None si el denominador es 0
    recall: float | None        # TP / (TP + FN); None si el denominador es 0
    f1: float | None            # 2PR / (P + R); None si P o R es None o P + R == 0

def iou(a: BoundingBox, b: BoundingBox) -> float: ...
def match_image(predictions: Sequence[PlateDetection], truths: Sequence[BoundingBox],
                threshold: float = IOU_THRESHOLD) -> DetectionCounts: ...
def summarize(per_image: Sequence[DetectionCounts]) -> DetectionMetrics: ...

# datasets/yolo_split.py — nuevo
IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})

@dataclass(frozen=True, slots=True)
class LabeledImage:
    name: str                       # nombre del archivo de imagen (sin ruta)
    image: ImageBGR
    boxes: tuple[BoundingBox, ...]  # en píxeles

def iter_split(dataset_dir: Path, split: str) -> Iterator[LabeledImage]: ...

# cli/detector_evaluation_commands.py — nuevo
DEFAULT_DATASET: Final[Path] = Path("training/detector/datasets/merged")
def register_detector_evaluation(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...
def cmd_evaluate_detector(args: argparse.Namespace, config: AppConfig) -> int: ...
```

## Comportamiento esperado
1. `iou(a, b)`: intersección / unión de áreas; 0.0 si no se solapan o si la unión es 0.
2. `match_image`: ordena las predicciones por confianza descendente (orden estable); para cada una, busca entre las
   verdades **aún no emparejadas** la de mayor IoU; si ese IoU ≥ `threshold` es TP y la verdad queda emparejada; si no, FP.
   FN = verdades sin emparejar. Sin predicciones ni verdades → `DetectionCounts(0, 0, 0)`.
3. `summarize`: suma los conteos; `images = len(per_image)`; calcula P, R y F1 según los tipos. Lista vacía →
   `EvaluationError("no hay imágenes para evaluar")`.
4. `iter_split(dataset_dir, split)`: `split` debe ser `"train"` o `"val"` (si no → `DatasetError`). Recorre
   `dataset_dir/images/<split>/` en orden de nombre (`sorted`), solo archivos cuya extensión en minúsculas esté en
   `IMAGE_SUFFIXES`; la etiqueta es `dataset_dir/labels/<split>/<stem>.txt` (si no existe → imagen sin placas, `boxes=()`).
   Imagen ilegible con `cv2.imread(..., cv2.IMREAD_COLOR)` → `DatasetError(f"imagen ilegible: {nombre}")`. Cada `YoloBox`
   (cualquier `class_id`; el dataset unificado solo tiene la clase 0) se convierte con `yolo_to_pixels`; las `None` se
   descartan. Carpeta `images/<split>` inexistente → `DatasetError(f"no existe el split {split}")`.
   Todas las rutas pasan por `resolve_within(dataset_dir, ...)`.
5. CLI `lector evaluate-detector [--dataset RUTA] [--split val] [--iou 0.5]` → `set_defaults(handler=cmd_evaluate_detector,
   network=False)` (sin `key`). `--dataset` por defecto `DEFAULT_DATASET`; `--split` con `choices=("train", "val")`,
   por defecto `"val"`; `--iou` `float`, por defecto `IOU_THRESHOLD`, fuera de (0, 1] → `EvaluationError`.
   - `dataset = resolve_within(config.root_dir, args.dataset)`;
     `detector = composition.build_plate_detector(config, composition.build_registry(config))`.
   - Por cada `LabeledImage`: si `min(alto, ancho) < 16` se omite (cuenta en `skipped`); si no,
     `match_image(detector.detect(item.image), item.boxes, args.iou)`.
   - `metrics = summarize(...)`; payload:
     `{"kind": "detector", "dataset": <nombre de la carpeta del dataset>, "split", "iou_threshold", "images", "skipped",
       "true_positives", "false_positives", "false_negatives", "precision", "recall", "f1",
       "backend": config.models.plate_detector.backend, "model_id": config.models.plate_detector.model_id}`;
     `write_report(_reports_dir(config), payload, SystemClock().now())`.
   - stdout: `images=… skipped=… tp=… fp=… fn=… precision=… recall=… f1=…` (con `_format_metric`) y `reporte=<nombre>`.
     Devuelve 0.

## Casos borde y manejo de errores
- Las imágenes del dataset son fotos completas o recortes de vehículo; el detector de placas corre sobre la imagen
  entera. Es una aproximación documentada: en producción corre dentro del recorte del vehículo (ADR-013).
- Ninguna ruta ni nombre de imagen va al reporte (solo el nombre de la carpeta del dataset).

## Tests de aceptación
```python
# tests/unit/evaluation/test_detection_metrics.py
from __future__ import annotations

import pytest

from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.detection_metrics import DetectionCounts, iou, match_image, summarize

A = BoundingBox(0, 0, 10, 10)


def test_iou() -> None:
    assert iou(A, A) == pytest.approx(1.0)
    assert iou(A, BoundingBox(5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert iou(A, BoundingBox(20, 20, 30, 30)) == 0.0


def test_match_is_greedy_by_confidence() -> None:
    low = PlateDetection(BoundingBox(1, 0, 11, 10), 0.4)
    high = PlateDetection(BoundingBox(0, 0, 10, 10), 0.9)
    assert match_image([low, high], [A]) == DetectionCounts(1, 1, 0)


def test_match_counts_misses_and_threshold() -> None:
    far = PlateDetection(BoundingBox(5, 0, 15, 10), 0.8)
    assert match_image([far], [A, BoundingBox(50, 50, 60, 60)]) == DetectionCounts(0, 1, 2)
    assert match_image([far], [A], threshold=0.3) == DetectionCounts(1, 0, 0)
    assert match_image([], []) == DetectionCounts(0, 0, 0)


def test_summarize() -> None:
    metrics = summarize([DetectionCounts(3, 1, 0), DetectionCounts(1, 0, 2), DetectionCounts(0, 0, 0)])
    assert metrics.images == 3
    assert metrics.precision == pytest.approx(0.8)
    assert metrics.recall == pytest.approx(4 / 6)
    assert metrics.f1 == pytest.approx(2 * 0.8 * (4 / 6) / (0.8 + 4 / 6))
    empty = summarize([DetectionCounts(0, 0, 0)])
    assert (empty.precision, empty.recall, empty.f1) == (None, None, None)
    with pytest.raises(EvaluationError):
        summarize([])
```
```python
# tests/unit/datasets/test_yolo_split.py
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.datasets.yolo_split import iter_split
from lector_placas.domain.errors import DatasetError


def make_dataset(root: Path) -> Path:
    (root / "images" / "val").mkdir(parents=True)
    (root / "labels" / "val").mkdir(parents=True)
    cv2.imwrite(str(root / "images" / "val" / "b.png"), np.zeros((100, 200, 3), np.uint8))
    cv2.imwrite(str(root / "images" / "val" / "a.jpg"), np.zeros((50, 50, 3), np.uint8))
    (root / "images" / "val" / "notas.txt").write_text("x", encoding="utf-8")
    (root / "labels" / "val" / "b.txt").write_text("0 0.5 0.5 0.5 0.2\n", encoding="utf-8")
    return root


def test_iter_split_reads_boxes_in_pixels(tmp_path: Path) -> None:
    items = list(iter_split(make_dataset(tmp_path), "val"))
    assert [item.name for item in items] == ["a.jpg", "b.png"]
    assert items[0].boxes == ()
    box = items[1].boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx((50, 40, 150, 60))
    assert items[1].image.shape == (100, 200, 3)


def test_iter_split_errors(tmp_path: Path) -> None:
    with pytest.raises(DatasetError):
        list(iter_split(tmp_path, "val"))
    with pytest.raises(DatasetError):
        list(iter_split(make_dataset(tmp_path), "test"))
```
```python
# tests/unit/cli/test_detector_evaluation_cli.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.infrastructure import network_guard

ROOT = Path(__file__).resolve().parents[3]


class FakeDetector:
    def detect(self, image):  # type: ignore[no-untyped-def]
        return [PlateDetection(BoundingBox(50, 40, 150, 60), 0.9)]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.setattr(composition, "build_registry", lambda config: None)
    monkeypatch.setattr(composition, "build_plate_detector", lambda config, registry: FakeDetector())
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    merged = tmp_path / "training" / "detector" / "datasets" / "merged"
    (merged / "images" / "val").mkdir(parents=True)
    (merged / "labels" / "val").mkdir(parents=True)
    for name in ("x1", "x2"):
        cv2.imwrite(str(merged / "images" / "val" / f"{name}.png"), np.zeros((100, 200, 3), np.uint8))
    (merged / "labels" / "val" / "x1.txt").write_text("0 0.5 0.5 0.5 0.2\n", encoding="utf-8")
    cv2.imwrite(str(merged / "images" / "val" / "tiny.png"), np.zeros((8, 8, 3), np.uint8))
    return tmp_path


def test_parser_defaults() -> None:
    args = cli_main.build_parser().parse_args(["evaluate-detector"])
    assert (args.split, args.iou, args.network) == ("val", 0.5, False)
    assert getattr(args, "key", None) is None


def test_evaluate_detector_writes_report(project: Path) -> None:
    code = cli_main.main(["--config", str(project / "config" / "lector.yaml"), "evaluate-detector"])
    assert code == 0
    report = next((project / "data" / "eval" / "reports").glob("report-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert (data["kind"], data["images"], data["skipped"]) == ("detector", 2, 1)
    assert (data["true_positives"], data["false_positives"], data["false_negatives"]) == (1, 1, 0)
    assert data["precision"] == pytest.approx(0.5)
    assert data["recall"] == pytest.approx(1.0)
    assert "x1" not in report.read_text(encoding="utf-8")


def test_invalid_iou_exits_nonzero(project: Path) -> None:
    code = cli_main.main(
        ["--config", str(project / "config" / "lector.yaml"), "evaluate-detector", "--iou", "1.5"]
    )
    assert code != 0
```

## Fuera de alcance
mAP por umbrales (lo reporta Ultralytics al entrenar, spec 030). Métricas desde la revisión (spec 038).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde, incluido `tests/architecture/test_dependency_rule.py`.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `evaluation/detection_metrics.py` no importa numpy, cv2 ni `lector_placas.datasets`; `datasets/yolo_split.py` no
      importa `lector_placas.evaluation`.
