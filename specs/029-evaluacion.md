# 029 - Evaluación: ground truth, métricas, CER, VRAM y reportes

## Objetivo
Implementar el módulo `lector_placas.evaluation` y los comandos `lector evaluate` y
`lector evaluate-ocr` que miden M-01..M-06 de docs/04-evaluacion.md sin exponer texto de placas.

## Depende de
028.

## Archivos rectores aplicables
- docs/04-evaluacion.md §2 (formato ground truth), §3 (métricas y emparejamiento), §4.
- reglas-seguridad.md SEG-04 (0600/0700), SEG-05/SEG-26 (reportes y consola sin placas), SEG-09 (nada de esto sale a la API), SEG-13, SEG-14.
- ARQUITECTURA.md §2 (capa Evaluación), §6. docs/02-contratos.md §7 (`EvaluationError` → código 8).

## Archivos a crear/modificar
- `src/lector_placas/evaluation/ground_truth.py`
- `src/lector_placas/evaluation/metrics.py`
- `src/lector_placas/evaluation/cer.py`
- `src/lector_placas/evaluation/vram_monitor.py`
- `src/lector_placas/evaluation/report.py`
- `src/lector_placas/evaluation/ocr_dataset.py`
- `src/lector_placas/cli/evaluation_commands.py`
- `src/lector_placas/cli/commands.py` (modificar: extraer `validated_video`)
- `src/lector_placas/cli/main.py` (modificar: registrar subcomandos)
- `tests/unit/evaluation/__init__.py`, `tests/unit/evaluation/test_ground_truth.py`, `test_metrics.py`,
  `test_cer.py`, `test_vram_monitor.py`, `test_report.py`, `test_ocr_dataset.py`
- `tests/unit/cli/test_evaluation_commands.py`

## Dependencias externas
Ninguna nueva (pydantic, opencv, stdlib `subprocess`, `threading`, `json`, `csv`).

## Interfaces y tipos involucrados
```python
# de domain: SightingRecord (ver CONTEXT.md), ReviewStatus, VehicleType, PLATE_TEXT_REGEX, EvaluationError
# de infrastructure: resolve_within, ensure_private_dir (007), sha256_file, validate_video_path (007),
#   PLATE_PATTERN (022, infrastructure/logging_setup.py), load_config/AppConfig (006), SystemClock (005)
# de cli/composition.py (028): data_dir, build_key_provider, build_repository, build_crop_store,
#   build_export_store, build_purge, build_process_video, build_registry, build_reader
# de application/process_video.py (024)
@dataclass(frozen=True, slots=True)
class RunResult: run_id: int; stats: RunStats        # RunStats.speed_factor -> float | None
# de application/ports.py
class PlateReader(Protocol):
    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]: ...
class PlateRepository(Protocol):
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
```
```python
# evaluation/ground_truth.py
class GroundTruthPlate(BaseModel):          # extra="forbid", frozen=True
    text: str
    vehicle_type: VehicleType
    first_seen_ms: int                       # >= 0
    last_seen_ms: int                        # >= first_seen_ms
    legible: bool                            # True => text cumple PLATE_TEXT_REGEX; False => text == ""
class GroundTruth(BaseModel):               # extra="forbid", frozen=True
    version: Literal[1]
    video_sha256: str                        # ^[0-9a-f]{64}$
    subset: Literal["street_day", "street_night", "parking", "fast"]
    camera: Literal["fixed", "handheld"]
    plates: tuple[GroundTruthPlate, ...]
def load_ground_truth(path: Path) -> GroundTruth: ...

# evaluation/metrics.py
TOLERANCE_MS: Final[int] = 1000
CONFIRMED_ONLY: Final[frozenset[ReviewStatus]] = frozenset({ReviewStatus.CONFIRMED})
ANY_STATUS: Final[frozenset[ReviewStatus]] = frozenset(
    {ReviewStatus.CONFIRMED, ReviewStatus.UNVERIFIED, ReviewStatus.CORRECTED})
@dataclass(frozen=True, slots=True)
class PlateMetrics:
    gt_legible: int
    confirmed_total: int
    confirmed_matched: int
    any_matched: int
    corrected_total: int
    @property
    def precision_confirmed(self) -> float | None: ...
    @property
    def recall_any(self) -> float | None: ...
    @property
    def recall_confirmed(self) -> float | None: ...
def overlaps(record: SightingRecord, plate: GroundTruthPlate, tolerance_ms: int) -> bool: ...
def greedy_match(records: Sequence[SightingRecord], plates: Sequence[GroundTruthPlate],
                 statuses: frozenset[ReviewStatus], tolerance_ms: int) -> int: ...
def compute_metrics(records: Sequence[SightingRecord], truth: GroundTruth,
                    tolerance_ms: int = TOLERANCE_MS) -> PlateMetrics: ...

# evaluation/cer.py
def levenshtein(a: str, b: str) -> int: ...
def character_error_rate(pairs: Sequence[tuple[str, str]]) -> float: ...   # (predicción, verdad)
def exact_match_rate(pairs: Sequence[tuple[str, str]]) -> float: ...

# evaluation/vram_monitor.py
QUERY: Final[tuple[str, ...]] = ("nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits")
INTERVAL_MS: Final[int] = 200
def parse_mib(line: str) -> int | None: ...
class VramMonitor:
    def __init__(self, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
                 popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen) -> None: ...
    def __enter__(self) -> VramMonitor: ...
    def __exit__(self, *exc_info: object) -> None: ...
    @property
    def peak_mib(self) -> int | None: ...

# evaluation/report.py
def write_report(reports_dir: Path, payload: Mapping[str, object], created_at: datetime) -> Path: ...

# evaluation/ocr_dataset.py
def read_ocr_annotations(csv_path: Path) -> list[tuple[Path, str]]: ...

# cli/evaluation_commands.py
def register_evaluation_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...
def cmd_evaluate(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_evaluate_ocr(args: argparse.Namespace, config: AppConfig) -> int: ...

# cli/commands.py (añadir)
def validated_video(config: AppConfig, path: Path) -> Path: ...
```

## Comportamiento esperado
1. `load_ground_truth(path)`: `json.loads(path.read_text("utf-8"))` y `GroundTruth.model_validate`; `OSError`,
   `json.JSONDecodeError` o `ValidationError` → `EvaluationError(f"ground truth inválido: {path.name}")` (sin volcar contenido).
   Validadores de `GroundTruthPlate` según los comentarios de la firma (`ValueError` con mensaje en español, sin el texto).
2. `overlaps(r, g, tol)` = `r.first_seen_ms <= g.last_seen_ms + tol and g.first_seen_ms <= r.last_seen_ms + tol`.
3. `greedy_match(records, plates, statuses, tol)`: `legibles = [p for p in plates if p.legible]`; se consideran los
   registros con `status in statuses`, ordenados por `(first_seen_ms, sighting_id)`; para cada uno se toma la **primera**
   placa legible no usada (en orden del ground truth) con `r.plate_text == p.text` y `overlaps`; se marca usada. Devuelve el
   número de parejas.
4. `compute_metrics`: `gt_legible` = legibles; `confirmed_total` = registros CONFIRMED;
   `confirmed_matched = greedy_match(..., CONFIRMED_ONLY, tol)`; `any_matched = greedy_match(..., ANY_STATUS, tol)`;
   `corrected_total` = registros CORRECTED. Propiedades: división o `None` si el denominador es 0
   (`precision_confirmed = confirmed_matched / confirmed_total`; `recall_any = any_matched / gt_legible`;
   `recall_confirmed = confirmed_matched / gt_legible`).
5. `levenshtein`: distancia de edición clásica (inserción, borrado, sustitución con costo 1), programación dinámica por filas.
   `character_error_rate(pairs)`: `sum(levenshtein(p, t)) / sum(len(t))`; lista vacía o suma de longitudes 0 → `EvaluationError`.
   `exact_match_rate(pairs)`: fracción con `p == t`; lista vacía → `EvaluationError`.
6. `parse_mib(line)`: `line.strip()`; entero si es un número entero no negativo, si no `None`.
7. `VramMonitor.__enter__`: línea base = primer entero de `run(list(QUERY), capture_output=True, text=True, check=True).stdout.splitlines()`;
   lanza `popen([*QUERY, "-lms", str(INTERVAL_MS)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)` y un
   `threading.Thread(daemon=True)` que lee `process.stdout` línea a línea añadiendo cada `parse_mib` no nulo a `samples`.
   `FileNotFoundError`, `subprocess.CalledProcessError` o salida sin enteros → `EvaluationError("nvidia-smi no disponible")`.
   Llamadas con `# noqa: S603` y comentario (argumentos fijos, sin shell).
   `__exit__`: `process.terminate()`, `process.wait(timeout=5)`, `thread.join(timeout=5)`.
   `peak_mib`: `None` si no hay muestras; si no `max(0, max(samples) - baseline)`.
8. `write_report(dir, payload, created_at)`: `ensure_private_dir(dir)`; `text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)`;
   si `PLATE_PATTERN.search(text)` → `EvaluationError("el reporte no puede contener placas")`;
   nombre `f"report-{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}.json"`; `resolve_within`; `os.open(..., O_WRONLY|O_CREAT|O_EXCL, 0o600)`;
   `FileExistsError`/`OSError` → `EvaluationError`. Devuelve la ruta.
9. `read_ocr_annotations(csv_path)`: `csv.DictReader`; exige columnas `image_path` y `plate_text` (si faltan → `EvaluationError`);
   por fila: `plate_text` debe cumplir `PLATE_TEXT_REGEX`; `image = resolve_within(csv_path.parent, Path(image_path))` (`UnsafePathError`
   se propaga); sin filas → `EvaluationError`.
10. `validated_video(config, path)` en `commands.py` = la llamada a `validate_video_path` que hoy hace `cmd_process`
    (y `cmd_process` pasa a usarla, sin cambiar su comportamiento).
11. `register_evaluation_commands(subparsers)`:
    - `evaluate --video PATH --ground-truth PATH [--profile NOMBRE] [--skip-vram]` → `handler=cmd_evaluate`, `network=False`.
    - `evaluate-ocr --crops PATH` → `handler=cmd_evaluate_ocr`, `network=False`.
    `main.build_parser` la llama después de registrar los subcomandos de la spec 028.
12. `cmd_evaluate`: `name, _ = config.profile(args.profile)`; `video = validated_video(config, args.video)`; `sha = sha256_file(video)`;
    `truth = load_ground_truth(resolve_within(config.root_dir, args.ground_truth))`; si `truth.video_sha256 != sha` →
    `EvaluationError("el ground truth no corresponde al video")`. Abre BD, crops, exports y purga igual que `cmd_process`
    (con `try/finally` y `repository.close()`); ejecuta `build_process_video(...).execute(video, sha)` dentro de
    `with VramMonitor() as monitor:` salvo `--skip-vram` (entonces `vram_peak_mib = None`). Obtiene los registros de la corrida
    paginando `list_sightings(None, 500, offset)` y filtrando `run_id`; `metrics = compute_metrics(records, truth)`.
    Payload: `{"kind": "video", "subset", "camera", "profile", "run_id", "gt_legible", "confirmed_total", "confirmed_matched",
    "any_matched", "corrected_total", "precision_confirmed", "recall_any", "recall_confirmed", "speed_factor", "vram_peak_mib"}`.
    `write_report(resolve_within(data_dir(config), Path("eval/reports")), payload, clock.now())`; escribe en stdout las métricas
    (`clave=valor`, 4 decimales o `n/d`) y el nombre del reporte.
13. `cmd_evaluate_ocr`: `pairs_src = read_ocr_annotations(resolve_within(config.root_dir, args.crops))`;
    `reader = composition.build_reader(config, composition.build_registry(config))`; en lotes de 64 lee cada imagen con
    `cv2.imread(str(p), cv2.IMREAD_COLOR)` (`None` → `EvaluationError("imagen ilegible: <nombre>")`) y llama `reader.read`;
    `pairs = [(pred.text, verdad)]`; payload `{"kind": "ocr", "samples": n, "cer": ..., "exact_match_rate": ..., "model_id": config.models.ocr.model_id}`;
    escribe el reporte en `data/eval/reports` y las métricas en stdout.

## Casos borde y manejo de errores
- Ninguna salida (consola, reporte, log) contiene texto de placa.
- `EvaluationError` → código de salida 8 (ya mapeado en spec 028).

## Tests de aceptación
```python
# tests/unit/evaluation/test_ground_truth.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.ground_truth import load_ground_truth

VALID = {
    "version": 1, "video_sha256": "a" * 64, "subset": "street_day", "camera": "fixed",
    "plates": [
        {"text": "ABC123", "vehicle_type": "car", "first_seen_ms": 1, "last_seen_ms": 2, "legible": True},
        {"text": "", "vehicle_type": "truck", "first_seen_ms": 3, "last_seen_ms": 4, "legible": False},
    ],
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "gt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_ground_truth(tmp_path: Path) -> None:
    truth = load_ground_truth(write(tmp_path, VALID))
    assert truth.camera == "fixed" and len(truth.plates) == 2


@pytest.mark.parametrize("plate_patch", [
    {"text": "abc123"}, {"text": "", "legible": True}, {"text": "ABC123", "legible": False},
    {"first_seen_ms": 5, "last_seen_ms": 2}, {"first_seen_ms": -1},
])
def test_invalid_plates(tmp_path: Path, plate_patch: dict[str, object]) -> None:
    data = json.loads(json.dumps(VALID))
    data["plates"][0].update(plate_patch)
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, data))


def test_invalid_file(tmp_path: Path) -> None:
    bad = tmp_path / "gt.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(EvaluationError):
        load_ground_truth(bad)
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, {**VALID, "subset": "otro"}))
```
```python
# tests/unit/evaluation/test_metrics.py
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.evaluation.ground_truth import GroundTruth, GroundTruthPlate
from lector_placas.evaluation.metrics import compute_metrics, overlaps

T0 = datetime(2026, 9, 24, tzinfo=UTC)
C, U, R, K = ReviewStatus.CONFIRMED, ReviewStatus.UNVERIFIED, ReviewStatus.REJECTED, ReviewStatus.CORRECTED


def rec(sid: int, text: str, first: int, last: int, status: ReviewStatus) -> SightingRecord:
    return SightingRecord(sid, 1, sid, first, last, VehicleType.CAR, text, text, 0.9, 0.9, 3,
                          status, (), (), None, T0, None)


def gt(text: str, first: int, last: int, legible: bool = True) -> GroundTruthPlate:
    return GroundTruthPlate(text=text, vehicle_type=VehicleType.CAR, first_seen_ms=first,
                            last_seen_ms=last, legible=legible)


TRUTH = GroundTruth(version=1, video_sha256="a" * 64, subset="street_day", camera="fixed", plates=(
    gt("ABC123", 1000, 3000), gt("XYZ98K", 5000, 6000), gt("DEF456", 8000, 9000),
    gt("", 10000, 11000, legible=False)))


def test_compute_metrics() -> None:
    records = [
        rec(1, "ABC123", 1200, 2800, C), rec(2, "XYZ98L", 5100, 5900, C),
        rec(3, "DEF456", 8100, 8900, U), rec(4, "ABC123", 20000, 21000, C),
        rec(5, "XYZ98K", 5000, 6000, R), rec(6, "XYZ98K", 5200, 5800, K),
    ]
    metrics = compute_metrics(records, TRUTH)
    assert (metrics.gt_legible, metrics.confirmed_total, metrics.confirmed_matched) == (3, 3, 1)
    assert (metrics.any_matched, metrics.corrected_total) == (3, 1)
    assert metrics.precision_confirmed == pytest.approx(1 / 3)
    assert metrics.recall_any == pytest.approx(1.0)
    assert metrics.recall_confirmed == pytest.approx(1 / 3)


def test_one_to_one_matching() -> None:
    records = [rec(1, "ABC123", 1000, 2000, C), rec(2, "ABC123", 1500, 2500, C)]
    assert compute_metrics(records, TRUTH).confirmed_matched == 1


def test_overlap_tolerance() -> None:
    plate = gt("XYZ98K", 5000, 6000)
    assert overlaps(rec(1, "XYZ98K", 4100, 4500, U), plate, 1000)
    assert not overlaps(rec(1, "XYZ98K", 3500, 3900, U), plate, 1000)


def test_empty_denominators() -> None:
    metrics = compute_metrics([], GroundTruth(version=1, video_sha256="a" * 64, subset="fast",
                                              camera="handheld", plates=()))
    assert metrics.precision_confirmed is None and metrics.recall_any is None
```
```python
# tests/unit/evaluation/test_cer.py
from __future__ import annotations

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.cer import character_error_rate, exact_match_rate, levenshtein


@pytest.mark.parametrize("a,b,d", [
    ("", "", 0), ("ABC123", "ABC123", 0), ("ABC123", "ABC128", 1), ("ABC12", "ABC123", 1),
    ("XBC123", "ABC12", 2), ("", "ABC", 3),
])
def test_levenshtein(a: str, b: str, d: int) -> None:
    assert levenshtein(a, b) == d


def test_rates() -> None:
    pairs = [("ABC123", "ABC123"), ("ABC128", "ABC123"), ("XYZ98", "XYZ98K")]
    assert character_error_rate(pairs) == pytest.approx(2 / 18)
    assert exact_match_rate(pairs) == pytest.approx(1 / 3)


def test_empty_raises() -> None:
    with pytest.raises(EvaluationError):
        character_error_rate([])
    with pytest.raises(EvaluationError):
        exact_match_rate([])
```
```python
# tests/unit/evaluation/test_vram_monitor.py
from __future__ import annotations

import io
import subprocess

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.vram_monitor import VramMonitor, parse_mib


class FakeProcess:
    def __init__(self, text: str) -> None:
        self.stdout = io.StringIO(text)
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        return 0


def fake_run(stdout: str):  # type: ignore[no-untyped-def]
    def run(args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args, 0, stdout=stdout)
    return run


def test_parse_mib() -> None:
    assert parse_mib(" 1500 \n") == 1500
    assert parse_mib("N/A") is None


def test_peak_above_baseline() -> None:
    process = FakeProcess("1000\n1500\nN/A\n1200\n")
    with VramMonitor(run=fake_run("800\n"), popen=lambda *a, **k: process) as monitor:
        pass
    assert monitor.peak_mib == 700
    assert process.terminated


def test_missing_nvidia_smi() -> None:
    def missing(args, **kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("nvidia-smi")
    with pytest.raises(EvaluationError):
        with VramMonitor(run=missing):
            pass
```
```python
# tests/unit/evaluation/test_report.py
from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.report import write_report

T0 = datetime(2026, 9, 24, 12, 0, 1, tzinfo=UTC)


def test_writes_private_json(tmp_path: Path) -> None:
    path = write_report(tmp_path / "reports", {"kind": "ocr", "cer": 0.02}, T0)
    assert path.name == "report-20260924T120001Z.json"
    assert json.loads(path.read_text(encoding="utf-8"))["cer"] == 0.02
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(EvaluationError):
        write_report(tmp_path / "reports", {"kind": "ocr"}, T0)


def test_rejects_plate_text(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError):
        write_report(tmp_path / "reports", {"nota": "ABC123"}, T0)
```
```python
# tests/unit/evaluation/test_ocr_dataset.py
from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError, UnsafePathError
from lector_placas.evaluation.ocr_dataset import read_ocr_annotations


def write_csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "annotations.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_reads_rows(tmp_path: Path) -> None:
    rows = read_ocr_annotations(write_csv(tmp_path, "image_path,plate_text\nimages/a.png,ABC123\n"))
    assert rows == [((tmp_path / "images" / "a.png").resolve(), "ABC123")]


@pytest.mark.parametrize("body,error", [
    ("image,plate_text\na.png,ABC123\n", EvaluationError),
    ("image_path,plate_text\na.png,abc\n", EvaluationError),
    ("image_path,plate_text\n", EvaluationError),
    ("image_path,plate_text\n../x.png,ABC123\n", UnsafePathError),
])
def test_invalid(tmp_path: Path, body: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        read_ocr_annotations(write_csv(tmp_path, body))
```
```python
# tests/unit/cli/test_evaluation_commands.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.cli import composition, main as cli_main
from lector_placas.domain.entities import OcrResult
from lector_placas.infrastructure import network_guard

ROOT = Path(__file__).resolve().parents[3]


class FakeReader:
    def read(self, plate_images):  # type: ignore[no-untyped-def]
        return [OcrResult("ABC123", (0.9,) * 6) for _ in plate_images]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.setattr(composition, "build_registry", lambda config: None)
    monkeypatch.setattr(composition, "build_reader", lambda config, registry: FakeReader())
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


def test_parser_registers_evaluation_commands() -> None:
    parser = cli_main.build_parser()
    args = parser.parse_args(["evaluate", "--video", "v.mp4", "--ground-truth", "g.json", "--skip-vram"])
    assert (args.video, args.ground_truth, args.skip_vram, args.network) == (
        Path("v.mp4"), Path("g.json"), True, False)
    assert parser.parse_args(["evaluate-ocr", "--crops", "c.csv"]).crops == Path("c.csv")


def test_evaluate_ocr_writes_report_without_plates(project: Path) -> None:
    crops = project / "data" / "eval" / "ocr_crops"
    (crops / "images").mkdir(parents=True)
    for name in ("a.png", "b.png"):
        cv2.imwrite(str(crops / "images" / name), np.zeros((20, 60, 3), np.uint8))
    (crops / "annotations.csv").write_text(
        "image_path,plate_text\nimages/a.png,ABC123\nimages/b.png,ABC128\n", encoding="utf-8")
    code = cli_main.main(["--config", str(project / "config" / "lector.yaml"),
                          "evaluate-ocr", "--crops", str(crops / "annotations.csv")])
    assert code == 0
    report = next((project / "data" / "eval" / "reports").glob("report-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["samples"] == 2
    assert data["cer"] == pytest.approx(1 / 12)
    assert data["exact_match_rate"] == pytest.approx(0.5)
    assert "ABC" not in report.read_text(encoding="utf-8")
```

## Fuera de alcance
Construcción del ground truth (manual, docs/04-evaluacion.md §2); reportes agregados multi-video.

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] Los tests de spec 028 siguen en verde tras extraer `validated_video`.
