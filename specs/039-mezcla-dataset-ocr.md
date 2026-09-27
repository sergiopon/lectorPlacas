# 039 - Entrenamiento: mezcla real + sintético con reparto seguro y evaluación de aceptación del OCR

## Objetivo
Construir, en el proyecto `training/ocr`, el dataset del primer fine-tuning real del OCR (ADR-014): volver a partir los
recortes reales en `train`/`val`/`test` **por componente** (mismo texto de placa o misma imagen de origen ⇒ misma
partición), añadir sintéticos solo a `train` con una cuota controlada (≤ 50 % del train y cuota de motos), y medir el
modelo candidato frente al modelo base sobre el `test` real con un criterio de aceptación explícito.

## Depende de
032 (proyecto `training/ocr`, `common.py`, `train.py`), 033 (generador sintético), 031 (dataset `ocr_colombia`).

## Archivos rectores aplicables
- ADR-014 (receta y criterio de aceptación), ADR-003 (OCR), ADR-011 (proyecto separado), ADR-012 (hash del modelo base).
- reglas-seguridad.md SEG-09 (datos reales nunca a la API externa), SEG-10 (tests solo con datos sintéticos),
  SEG-11 (`training/**/datasets/` y `training/**/runs/` ignorados), SEG-04 (directorios 0700, archivos 0600),
  SEG-05 (consola y reportes sin texto de placa).
- docs/04-evaluacion.md §3 (M-04) y §5.3–5.4 (metas y partición). ARQUITECTURA.md §6 (convenciones).
- `training/ocr` es un proyecto uv independiente: **no importa `lector_placas`** (la distancia de edición se implementa aquí).

## Archivos a crear/modificar
- `training/ocr/ocr_training/mix_split.py` (nuevo: lógica pura de agrupación, reparto y cuota)
- `training/ocr/ocr_training/mix_dataset.py` (nuevo: carga, escritura y CLI de la mezcla)
- `training/ocr/ocr_training/evaluate_ocr.py` (nuevo: métricas, criterio de aceptación y CLI)
- `training/ocr/tests/test_mix_dataset.py` (nuevo)
- `training/ocr/tests/test_evaluate_ocr.py` (nuevo)

No se modifican `common.py`, `train.py`, `synthetic_plates.py`, `pyproject.toml` ni `uv.lock`.

## Dependencias externas
Ninguna nueva. Se usan las del entorno de la spec 032: `opencv-python==4.14.0.94`, `numpy`, `fast-plate-ocr==1.1.0`
(solo `LicensePlateRecognizer`, importado dentro de `onnx_predictor`) y la biblioteca estándar
(`hashlib`, `math`, `random`, `json`, `csv`, `shutil`, `os`, `datetime`).

## Interfaces y tipos involucrados
API verificada de fast-plate-ocr 1.1.0 (código instalado en `training/ocr/.venv`):
```python
# from fast_plate_ocr import LicensePlateRecognizer
# LicensePlateRecognizer(onnx_model_path=..., plate_config_path=..., providers=["CPUExecutionProvider"])
# .run(list_of_rgb_uint8_arrays) -> list[PlatePrediction]; PlatePrediction.plate: str (sin relleno final "_")
# Los arreglos en memoria se asumen en el modo de color del config (rgb); el runtime (spec 017) convierte BGR→RGB.
```
De `ocr_training/common.py` (spec 032): `DATASETS_DIR`, `TRAINING_DIR`, `RUNS_DIR`, `PROJECT_ROOT`, `TrainingError`,
`validate_annotations`, `require_asset`, `sha256_file`, `check_ocr_onnx`.

```python
# ocr_training/mix_split.py — a implementar
MOTO_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]?$")    # co_moto (LLLDDL) y co_moto_antigua (LLLDD)
MOTOCARRO_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9]{3}[A-Z]{3}$")     # co_motocarro (DDDLLL)
ROBOFLOW_NAME_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^(?P<source>.+?)__(?P<stem>.+)\.rf\.[0-9a-fA-F]+_(?P<index>\d+)\.png$")    # nombres que escribe chars_to_ocr
CATEGORIES: Final[tuple[str, ...]] = ("moto", "motocarro", "other")
SPLITS: Final[tuple[str, ...]] = ("train", "val", "test")
SYNTHETIC_MOTOCARRO_SHARE: Final[float] = 0.15

@dataclass(frozen=True, slots=True)
class Sample:
    image: Path      # ruta absoluta resuelta de la imagen de origen
    text: str        # plate_text
    origin: str      # grupo de imagen de origen (ver origin_group)
    real: bool       # False para sintéticos

def category(text: str) -> str: ...
def origin_group(source_name: str, relative_path: str) -> str: ...
def components(samples: Sequence[Sample]) -> list[list[Sample]]: ...
def component_category(component: Sequence[Sample]) -> str: ...
def split_components(comps: Sequence[Sequence[Sample]], val_fraction: float, test_fraction: float,
                     seed: int) -> dict[str, list[list[Sample]]]: ...
def select_synthetic(synthetic: Sequence[Sample], real_train: Sequence[Sample], excluded_texts: AbstractSet[str],
                     ratio: float, min_moto_fraction: float, seed: int) -> list[Sample]: ...
```
```python
# ocr_training/mix_dataset.py — a implementar
MANIFEST_NAME: Final[str] = "manifest.json"
GROUPS_NAME: Final[str] = "groups.csv"

def load_real(source_dir: Path) -> list[Sample]: ...
def load_synthetic(source_dir: Path) -> list[Sample]: ...
def build_mix(output_dir: Path, real_dirs: Sequence[Path], synthetic_dir: Path | None, val_fraction: float,
              test_fraction: float, synthetic_ratio: float, min_moto_fraction: float, seed: int) -> dict[str, object]: ...
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```
```python
# ocr_training/evaluate_ocr.py — a implementar
BASELINE_MODEL_ID: Final[str] = "fpo-cct-xs-v2-global"
BASELINE_ONNX: Final[Path] = PROJECT_ROOT / "models" / "fpo-cct-xs-v2-global" / "cct_xs_v2_global.onnx"
BASELINE_SHA256: Final[str] = "8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44"   # ADR-012
REPORTS_DIR: Final[Path] = RUNS_DIR / "reports"
MAX_CER: Final[float] = 0.03            # M-04
MAX_CER_UPPER: Final[float] = 0.05      # cota superior del IC 95 %
MIN_TEST_SAMPLES: Final[int] = 100
BOOTSTRAP_ROUNDS: Final[int] = 2000
EVAL_BATCH_SIZE: Final[int] = 64
Predictor = Callable[[Sequence[npt.NDArray[np.uint8]]], list[str]]
PredictorFactory = Callable[[Path, Path], Predictor]      # (modelo onnx, plate config) -> predictor

@dataclass(frozen=True, slots=True)
class ModelMetrics:
    samples: int
    cer: float
    exact_match_rate: float
    cer_ci95: tuple[float, float]
    cer_by_category: dict[str, float | None]     # claves = CATEGORIES; None si no hay muestras
    samples_by_category: dict[str, int]

def levenshtein(a: str, b: str) -> int: ...
def normalize_prediction(text: str) -> str: ...
def read_split(csv_path: Path) -> list[tuple[Path, str, str]]: ...
def compute_metrics(predictions: Sequence[str], truths: Sequence[str], groups: Sequence[str], seed: int,
                    rounds: int = BOOTSTRAP_ROUNDS) -> ModelMetrics: ...
def decide(candidate: ModelMetrics, baseline: ModelMetrics) -> list[str]: ...
def onnx_predictor(model_path: Path, plate_config: Path) -> Predictor: ...
def evaluate(crops_csv: Path, candidate_onnx: Path, baseline_onnx: Path, plate_config: Path, seed: int,
             predictor_factory: PredictorFactory = onnx_predictor) -> dict[str, object]: ...
def write_report(report: Mapping[str, object], reports_dir: Path, now: datetime) -> Path: ...
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

## Comportamiento esperado

### `mix_split.py` (sin E/S)
1. `category(text)`: `"moto"` si `MOTO_REGEX.fullmatch`; si no, `"motocarro"` si `MOTOCARRO_REGEX.fullmatch`; si no, `"other"`.
2. `origin_group(source_name, relative_path)`: `name = PurePosixPath(relative_path).name`; si
   `ROBOFLOW_NAME_REGEX.fullmatch(name)` → `f"{source_name}/{m['source']}/{m['stem']}"` (todas las copias `.rf.<hash>` y
   todos los recortes de la misma imagen de origen comparten grupo); si no → `f"{source_name}/{relative_path}"`.
3. `components(samples)`: unión-búsqueda sobre los índices de `samples`; dos muestras quedan en el mismo componente si
   comparten `text` **o** `origin` (transitivamente). Orden normativo: los componentes se ordenan por el menor índice de
   sus muestras y, dentro de cada componente, las muestras van en orden de índice creciente.
4. `component_category(component)`: `"moto"` si alguna muestra es `moto`; si no, `"motocarro"` si alguna lo es; si no, `"other"`.
5. `split_components(comps, val_fraction, test_fraction, seed)`:
   - Exige `val_fraction > 0`, `test_fraction > 0` y `val_fraction + test_fraction < 1`; si no → `TrainingError`.
   - Resultado `{"train": [], "val": [], "test": []}`. Para cada `cat` de `CATEGORIES`, en ese orden: toma los
     componentes con `component_category == cat` y los ordena por
     `hashlib.sha256(f"{seed}\n{min(s.origin for s in comp)}".encode("utf-8")).hexdigest()`; con `n` componentes,
     `n_test = math.floor(n * test_fraction + 0.5)` y `n_val = math.floor(n * val_fraction + 0.5)`; los primeros
     `n_test` se añaden a `test`, los `n_val` siguientes a `val` y el resto a `train`.
   - Si alguna de las tres listas queda vacía → `TrainingError("partición vacía: <split>")`.
6. `select_synthetic(synthetic, real_train, excluded_texts, ratio, min_moto_fraction, seed)`:
   - Exige `0 <= ratio <= 1` (sintéticos ≤ 50 % del train) y `0 <= min_moto_fraction < 1`; si no → `TrainingError`.
   - `target = math.floor(len(real_train) * ratio)`; si `target == 0` devuelve `[]`.
   - `real_moto` = muestras de `real_train` con `category == "moto"`;
     `needed = max(0, math.ceil(min_moto_fraction * (len(real_train) + target) - 1e-9) - real_moto)`;
     `n_moto = min(needed, target)`; `rest = target - n_moto`;
     `n_motocarro = math.floor(rest * SYNTHETIC_MOTOCARRO_SHARE + 0.5)`; `n_other = rest - n_motocarro`.
   - Descarta los sintéticos cuyo `text` está en `excluded_texts` (textos reales de `val`/`test`) y reparte el resto en
     tres pozos por `category`, conservando el orden de entrada.
   - `rng = random.Random(seed)`; para cada `cat` de `CATEGORIES`, en orden: `pool = list(pozo)`, `rng.shuffle(pool)`;
     si `len(pool) < n_cat` → `TrainingError(f"faltan sintéticos de {cat}: se necesitan {n_cat}, hay {len(pool)}")`;
     añade `pool[:n_cat]`. Devuelve la selección en el orden moto, motocarro, other.

### `mix_dataset.py`
Usa la variable de módulo `DATASETS_DIR` importada de `common` (los tests la sustituyen con `monkeypatch`). Una ruta
"dentro de `DATASETS_DIR`" significa: `DATASETS_DIR.resolve()` está en `path.resolve().parents`.

7. `load_real(source_dir)`:
   - `source_dir` debe existir, ser directorio y estar dentro de `DATASETS_DIR`; si contiene `MANIFEST_NAME` (es una
     salida de esta herramienta, con sintéticos) → `TrainingError("no se mezcla una salida de mix_dataset")`.
   - CSV a leer: `[source_dir / "annotations.csv"]` si existe (formato de `lector dataset export-reviewed`, spec 035);
     si no, los `source_dir / s / "annotations.csv"` existentes para `s` en `("train", "val")`. Ninguno → `TrainingError`.
   - Cada CSV pasa por `validate_annotations`. Por fila: `image = (csv.parent / image_path).resolve()`,
     `origin = origin_group(source_dir.name, image.relative_to(source_dir.resolve()).as_posix())`,
     `Sample(image, plate_text, origin, True)`. Orden: CSV en el orden indicado y filas en orden de archivo.
8. `load_synthetic(source_dir)`: dentro de `DATASETS_DIR`; lee **solo** `source_dir / "train" / "annotations.csv"`
   (inexistente → `TrainingError`; su `val` se ignora: los sintéticos nunca van a `val` ni a `test`); `validate_annotations`;
   `Sample(image, plate_text, f"syn/{image_path}", False)`.
9. `build_mix(...)`:
   1. Validaciones previas, **antes de crear nada**: `output_dir` dentro de `DATASETS_DIR` y sin existir; `real_dirs` no vacío
      y con nombres (`.name`) únicos; cada error → `TrainingError`.
   2. `real = load_real(d)` concatenado para cada `d` de `real_dirs`, en orden; `comps = components(real)`;
      `parts = split_components(comps, val_fraction, test_fraction, seed)`.
   3. `real_train` = muestras de `parts["train"]` aplanadas en orden; `excluded` = textos de las muestras de `val` y `test`.
      `chosen = select_synthetic(load_synthetic(synthetic_dir), real_train, excluded, synthetic_ratio, min_moto_fraction, seed)`
      si `synthetic_dir` no es `None`; si no, `chosen = []`.
   4. Escritura: `output_dir.mkdir(parents=True)` y `os.chmod(output_dir, 0o700)`. Para cada split de `SPLITS`:
      directorio `<split>/images/` (ambos con `mkdir()` y `chmod 0o700`). Filas del split = muestras de sus componentes
      aplanadas en orden y, solo en `train`, después las de `chosen`. La fila `i` (0-based, contada en el split) copia su
      imagen con `shutil.copyfile` a `images/{"real" if s.real else "syn"}_{i:06d}{s.image.suffix.lower()}` y le aplica
      `chmod 0o600`. `annotations.csv` (UTF-8, `lineterminator="\n"`, cabecera `image_path,plate_text`, rutas
      `images/<nombre>`), `chmod 0o600`. En `val` y `test`, además `groups.csv` (misma forma, cabecera
      `image_path,group_id`, `group_id = f"g{k:05d}"` con `k` = índice del componente dentro del split), `chmod 0o600`.
   5. Manifiesto (solo tipos JSON; **sin textos de placa**): `{"version": 1, "seed", "val_fraction", "test_fraction",
      "synthetic_ratio", "min_moto_fraction", "real_sources": [nombres de real_dirs], "synthetic_source": nombre o None,
      "components": len(comps), "splits": {split: {"real", "synthetic", "moto", "motocarro", "other", "components"}},
      "train_synthetic_fraction", "train_moto_fraction", "moto_target_met"}`, donde `moto/motocarro/other` cuentan todas
      las filas del split por `category`, `train_synthetic_fraction = synthetic / (real + synthetic)` de train,
      `train_moto_fraction = moto / (real + synthetic)` de train y
      `moto_target_met = train_moto_fraction >= min_moto_fraction - 1e-9`. Se escribe en `output_dir / MANIFEST_NAME`
      con `json.dumps(manifest, indent=2, sort_keys=True)` y `chmod 0o600`.
   6. `validate_annotations` de los tres `annotations.csv`. Devuelve el manifiesto.
   7. Si la escritura (pasos 4–6) lanza cualquier excepción, `shutil.rmtree(output_dir, ignore_errors=True)` y se relanza.
10. CLI: `--real` (Path, `action="append"`, obligatorio, relativo a `DATASETS_DIR`), `--synthetic` (Path, opcional),
    `--output` (Path, obligatorio), `--val-fraction` (float, 0.10), `--test-fraction` (float, 0.20),
    `--synthetic-ratio` (float, 1.0), `--min-moto-fraction` (float, 0.20), `--seed` (int, 0). `main` llama
    `build_mix(DATASETS_DIR / args.output, [DATASETS_DIR / r for r in args.real], DATASETS_DIR / args.synthetic o None, ...)`
    e imprime, por split, `f"{split}: real={..} synthetic={..} moto={..} components={..}"` y la línea
    `f"train_synthetic_fraction={x:.3f} train_moto_fraction={y:.3f} moto_target_met={b}"`. Nunca imprime textos de placa.
    Devuelve 0. `if __name__ == "__main__": raise SystemExit(main())`.

### `evaluate_ocr.py`
11. `levenshtein(a, b)`: distancia de edición con costo 1 por inserción, borrado y sustitución.
12. `normalize_prediction(text)`: `""` si contiene `"_"` o no cumple `^[A-Z0-9]{0,10}$`; si no, `text` (misma regla que el
    adaptador de runtime, spec 017).
13. `read_split(csv_path)`:
    - `csv_path.parent.name != "test"` → `TrainingError("la aceptación se mide en el split test")`.
    - `validate_annotations(csv_path)`; `csv_path.parent / "groups.csv"` inexistente → `TrainingError("falta groups.csv")`;
      sus columnas deben ser exactamente `image_path,group_id` (si no → `TrainingError`).
    - Por fila de `annotations.csv`: si `PurePosixPath(image_path).name.startswith("syn_")` →
      `TrainingError("el split de evaluación contiene sintéticos")`; si el `image_path` no está en `groups.csv` →
      `TrainingError`. Devuelve `[((csv_path.parent / image_path).resolve(), plate_text, group_id), ...]` en orden de archivo.
14. `compute_metrics(predictions, truths, groups, seed, rounds)`:
    - Longitudes iguales y no vacías; si no → `TrainingError`.
    - `d_i = levenshtein(pred_i, truth_i)`; `cer = Σd / Σlen(truth)`; `exact_match_rate = #(pred == truth) / n`.
    - IC 95 % por bootstrap **por grupo** (errores correlacionados dentro del mismo vehículo): por grupo, en orden de
      primera aparición, `(Σd, Σlen)`; `rng = random.Random(seed)`; `rounds` veces: `len(grupos)` extracciones con
      `rng.choice(lista_de_grupos)` (con reemplazo) y `Σd/Σlen` de la muestra; se ordenan y
      `cer_ci95 = (stats[math.floor(0.025 * rounds)], stats[math.ceil(0.975 * rounds) - 1])`.
    - `cer_by_category[cat]`: CER de las filas cuya verdad tiene `category == cat` (import de `mix_split`), o `None` si no hay;
      `samples_by_category[cat]`: número de filas. Claves en el orden de `CATEGORIES`.
15. `decide(candidate, baseline)` devuelve los motivos de rechazo (lista vacía = aceptado), en este orden:
    - `candidate.samples < MIN_TEST_SAMPLES` → `f"muestra insuficiente: {samples} < {MIN_TEST_SAMPLES}"`
    - `candidate.cer > MAX_CER` → `f"CER {cer:.4f} > {MAX_CER}"`
    - `candidate.cer_ci95[1] > MAX_CER_UPPER` → `f"cota superior del IC 95 % {upper:.4f} > {MAX_CER_UPPER}"`
    - `candidate.cer >= baseline.cer` → `"no mejora el CER del modelo base"`
    - `candidate.exact_match_rate < baseline.exact_match_rate` → `"empeora la coincidencia exacta del modelo base"`
16. `onnx_predictor(model_path, plate_config)`: importa `LicensePlateRecognizer` dentro de la función, lo construye con
    `onnx_model_path=model_path, plate_config_path=plate_config, providers=["CPUExecutionProvider"]` (la GPU queda libre
    para entrenar) y devuelve `lambda images: [p.plate for p in recognizer.run(list(images))]`.
17. `evaluate(crops_csv, candidate_onnx, baseline_onnx, plate_config, seed, predictor_factory)`:
    - `rows = read_split(crops_csv)`; cada imagen con `cv2.imread` (`None` → `TrainingError`) y `cv2.cvtColor(..., cv2.COLOR_BGR2RGB)`.
    - Para `candidate_onnx` y luego `baseline_onnx`: `predictor = predictor_factory(modelo, plate_config)`; predicciones en
      lotes de `EVAL_BATCH_SIZE`; si un lote devuelve otro número de textos → `TrainingError`; cada texto pasa por
      `normalize_prediction`. `compute_metrics(preds, truths, groups, seed)`.
    - `reasons = decide(cand, base)`; `warnings`: si `cand.cer_by_category["moto"]` y `base.cer_by_category["moto"]` no son
      `None` y el del candidato es mayor → `f"regresión en motos (muestra pequeña: {n} recortes)"`.
    - Devuelve `{"version": 1, "samples": n, "candidate": dataclasses.asdict(cand), "baseline": dataclasses.asdict(base),
      "accepted": not reasons, "reasons": reasons, "warnings": warnings}` (sin textos de placa).
18. `write_report(report, reports_dir, now)`: `now` sin zona horaria → `TrainingError`; `reports_dir.mkdir(parents=True,
    exist_ok=True, mode=0o700)` (SEG-04); archivo `ocr-eval-{now.astimezone(UTC):%Y%m%dT%H%M%SZ}.json` creado con
    `os.open(path, O_WRONLY | O_CREAT | O_EXCL, 0o600)` (`FileExistsError` → `TrainingError("el reporte ya existe")`) y
    contenido `json.dumps(report, indent=2, sort_keys=True)`. Devuelve la ruta.
19. CLI: `--crops` (Path, obligatorio, relativo a `DATASETS_DIR`), `--candidate` (Path, obligatorio, relativo a
    `TRAINING_DIR`, p. ej. `runs/<name>/<fecha>/best.onnx`), `--seed` (int, 0). `main`:
    1. `crops` fuera de `DATASETS_DIR` → `TrainingError`; `candidate` inexistente → `TrainingError`; `check_ocr_onnx(candidate)`.
    2. `plate_config = require_asset("cct_xs_v2_global_plate_config.yaml")`.
    3. `BASELINE_ONNX` inexistente o `sha256_file` distinto de `BASELINE_SHA256` →
       `TrainingError("modelo base no verificado: ejecute lector models fetch en la raíz")`.
    4. `report = evaluate(...)`; añade `report["candidate_sha256"] = sha256_file(candidate)` y
       `report["baseline_model_id"] = BASELINE_MODEL_ID`; `write_report(report, REPORTS_DIR, datetime.now(UTC))`.
    5. Imprime `f"candidato: muestras={n} cer={c:.4f} ic95=[{lo:.4f}, {hi:.4f}] exacta={e:.4f}"`,
       `f"base: cer={c:.4f} exacta={e:.4f}"`, `decision=ACEPTAR` o `decision=RECHAZAR`, una línea `motivo: <m>` por motivo,
       una `aviso: <w>` por aviso y `reporte=<nombre>`. Devuelve 0 si se acepta y 1 si se rechaza.
       `if __name__ == "__main__": raise SystemExit(main())`.

## Casos borde y manejo de errores
- Mismos argumentos y `seed` ⇒ mismos CSV (determinismo). El reparto no depende de los sintéticos: cambiar
  `--synthetic`/`--synthetic-ratio` con la misma `seed` deja idénticos `val` y `test`.
- Un vehículo con varias fotos renombradas por Roboflow (distinto `.rf.<hash>`, distinto grupo) queda unido por su texto;
  dos placas de la misma foto quedan unidas por su grupo de origen.
- Los sintéticos cuyo texto coincide con una placa real de `val`/`test` se descartan antes de seleccionar.
- Si faltan sintéticos de alguna categoría, el operador genera más con `synthetic_plates --count` mayor (no se relaja la cuota).
- Ni la consola, ni el manifiesto, ni el reporte contienen textos de placa (solo conteos, tasas y nombres de carpeta).

## Tests de aceptación
```python
# training/ocr/tests/test_mix_dataset.py
from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest

from ocr_training import mix_dataset as md
from ocr_training import mix_split as ms
from ocr_training.common import TrainingError, validate_annotations


def sample(text: str, origin: str, real: bool = True) -> ms.Sample:
    return ms.Sample(Path(f"/x/{origin}_{text}.png"), text, origin, real)


def write_split(split_dir: Path, rows: Sequence[tuple[str, str]]) -> None:
    (split_dir / "images").mkdir(parents=True, exist_ok=True)
    for name, _ in rows:
        assert cv2.imwrite(str(split_dir / "images" / name), np.full((20, 40, 3), 100, np.uint8))
    with (split_dir / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("image_path", "plate_text"))
        writer.writerows((f"images/{name}", text) for name, text in rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rf(group: int, index: int = 0) -> str:
    return f"src__{group:04d}_jpg.rf.ab12cd_{index}.png"


def real_source(root: Path) -> Path:
    source = root / "real1"
    texts = [f"CAR{i:03d}" for i in range(26)] + [f"MOT{i:02d}A" for i in range(4)]
    rows = [(rf(i), text) for i, text in enumerate(texts)]
    write_split(source / "train", [*rows[:25], (rf(1, 1), "CAR900")])
    write_split(source / "val", [*rows[25:], (rf(100), "CAR000")])
    return source


def synthetic_source(root: Path) -> Path:
    source = root / "syn"
    names = iter(f"syn_{i:06d}.png" for i in range(1000))
    rows = [(next(names), f"SYM{i:02d}A") for i in range(60)]
    rows += [(next(names), f"{i:03d}SYN") for i in range(60)]
    rows += [(next(names), f"SYN{i:03d}") for i in range(60)]
    write_split(source / "train", rows)
    write_split(source / "val", [("val_000000.png", "ZZZ999")])
    return source


@pytest.mark.parametrize(("text", "expected"), [
    ("ABC123", "other"), ("ABC12D", "moto"), ("ABC12", "moto"), ("123ABC", "motocarro"), ("R12345", "other"),
])
def test_category(text: str, expected: str) -> None:
    assert ms.category(text) == expected


def test_origin_group() -> None:
    name = "train/images/ocr_placas_colombia__0069_jpg.rf.fe61_6.png"
    assert ms.origin_group("ocr_colombia", name) == "ocr_colombia/ocr_placas_colombia/0069_jpg"
    assert ms.origin_group("own", "images/000001.png") == "own/images/000001.png"


def test_components_link_text_and_origin() -> None:
    a, b = sample("AAA111", "o1"), sample("AAA111", "o2")
    c, d = sample("BBB222", "o2"), sample("CCC333", "o3")
    result = ms.components([d, a, b, c])
    assert [[s.text for s in comp] for comp in result] == [["CCC333"], ["AAA111", "AAA111", "BBB222"]]


def test_split_components_is_stratified_and_deterministic() -> None:
    comps = [[sample(f"AAA{i:03d}", f"o{i}")] for i in range(40)]
    comps += [[sample(f"MOT{i:02d}A", f"m{i}")] for i in range(10)]
    result = ms.split_components(comps, 0.1, 0.2, 0)
    assert [len(result[s]) for s in ms.SPLITS] == [35, 5, 10]
    moto = {s: sum(ms.component_category(c) == "moto" for c in result[s]) for s in ms.SPLITS}
    assert moto == {"train": 7, "val": 1, "test": 2}
    assert ms.split_components(comps, 0.1, 0.2, 0) == result
    assert ms.split_components(comps, 0.1, 0.2, 1)["test"] != result["test"]
    origins = [{c[0].origin for c in result[s]} for s in ms.SPLITS]
    assert sum(len(o) for o in origins) == 50 and len(set().union(*origins)) == 50


@pytest.mark.parametrize(("val", "test"), [(0.0, 0.2), (0.1, 0.0), (0.5, 0.5)])
def test_split_components_invalid_fractions(val: float, test: float) -> None:
    with pytest.raises(TrainingError):
        ms.split_components([[sample("AAA000", "o0")]], val, test, 0)


def test_split_components_empty_partition() -> None:
    with pytest.raises(TrainingError):
        ms.split_components([[sample("AAA000", "o0")], [sample("AAA001", "o1")]], 0.1, 0.2, 0)


def real_train() -> list[ms.Sample]:
    return [sample(f"AAA{i:03d}", f"r{i}") for i in range(76)] + [sample(f"MOT{i:02d}A", f"q{i}") for i in range(4)]


def synthetic_pool(others: int = 100) -> list[ms.Sample]:
    pool = [sample(f"SYM{i:02d}A", f"s{i}", False) for i in range(100)]
    pool += [sample(f"{i:03d}SYN", f"t{i}", False) for i in range(100)]
    return pool + [sample(f"SYN{i:03d}", f"u{i}", False) for i in range(others)]


def test_select_synthetic_quota() -> None:
    chosen = ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 1.0, 0.2, 0)
    assert Counter(ms.category(s.text) for s in chosen) == Counter({"other": 44, "moto": 28, "motocarro": 8})
    assert all(not s.real for s in chosen)
    assert ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 1.0, 0.2, 0) == chosen
    half = ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 0.5, 0.2, 0)
    assert Counter(ms.category(s.text) for s in half) == Counter({"other": 17, "moto": 20, "motocarro": 3})
    assert ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 0.0, 0.2, 0) == []


def test_select_synthetic_excludes_eval_texts() -> None:
    chosen = ms.select_synthetic(synthetic_pool(others=45), real_train(), frozenset({"SYN000"}), 1.0, 0.2, 0)
    others = {s.text for s in chosen if ms.category(s.text) == "other"}
    assert len(others) == 44 and "SYN000" not in others


@pytest.mark.parametrize(("ratio", "moto"), [(1.5, 0.2), (-0.1, 0.2), (1.0, 1.0)])
def test_select_synthetic_invalid(ratio: float, moto: float) -> None:
    with pytest.raises(TrainingError):
        ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), ratio, moto, 0)


def test_select_synthetic_shortage() -> None:
    pool = [sample(f"SYM{i:02d}A", f"s{i}", False) for i in range(5)] + synthetic_pool()[100:]
    with pytest.raises(TrainingError):
        ms.select_synthetic(pool, real_train(), frozenset(), 1.0, 0.2, 0)


def test_load_real_reviewed_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    write_split(tmp_path / "own", [("000000.png", "OWN001"), ("000001.png", "OWN001")])
    samples = md.load_real(tmp_path / "own")
    assert [s.origin for s in samples] == ["own/images/000000.png", "own/images/000001.png"]
    assert all(s.real and s.image.is_file() for s in samples)
    assert len(ms.components(samples)) == 1


def test_build_mix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real, syn, out = real_source(tmp_path), synthetic_source(tmp_path), tmp_path / "mix"
    manifest = md.build_mix(out, [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert [manifest["splits"][s]["components"] for s in ms.SPLITS] == [21, 3, 6]
    splits = {s: read_rows(out / s / "annotations.csv") for s in ms.SPLITS}
    for split, rows in splits.items():
        assert validate_annotations(out / split / "annotations.csv") == len(rows)
    train_real = [r for r in splits["train"] if r["image_path"].startswith("images/real_")]
    train_syn = [r for r in splits["train"] if r["image_path"].startswith("images/syn_")]
    assert len(train_real) + len(train_syn) == len(splits["train"])
    assert len(train_syn) == len(train_real) == manifest["splits"]["train"]["real"]
    assert manifest["splits"]["train"]["synthetic"] == len(train_syn)
    for split in ("val", "test"):
        assert all(r["image_path"].startswith("images/real_") for r in splits[split])
        groups = read_rows(out / split / "groups.csv")
        assert [g["image_path"] for g in groups] == [r["image_path"] for r in splits[split]]
        assert len({g["group_id"] for g in groups}) == manifest["splits"][split]["components"]
    assert len(train_real) + len(splits["val"]) + len(splits["test"]) == 32
    texts = {s: {r["plate_text"] for r in rows if r["image_path"].startswith("images/real_")}
             for s, rows in splits.items()}
    assert not texts["train"] & texts["val"] and not texts["train"] & texts["test"] and not texts["val"] & texts["test"]
    where = {r["plate_text"]: s for s, rows in splits.items() for r in rows if r["image_path"].startswith("images/real_")}
    assert where["CAR900"] == where["CAR001"]
    assert all(r["plate_text"] != "ZZZ999" for rows in splits.values() for r in rows)
    assert manifest["moto_target_met"] is True and manifest["train_moto_fraction"] >= 0.2
    assert (out.stat().st_mode & 0o777) == 0o700
    assert (out / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert (out / "train" / "images" / "real_000000.png").stat().st_mode & 0o777 == 0o600
    with pytest.raises(TrainingError):
        md.build_mix(out, [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    with pytest.raises(TrainingError):
        md.build_mix(tmp_path.parent / "fuera_039", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    with pytest.raises(TrainingError):
        md.build_mix(tmp_path / "mix2", [out], None, 0.1, 0.2, 1.0, 0.2, 0)
    assert not (tmp_path / "mix2").exists()


def test_build_mix_is_deterministic_and_split_ignores_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real, syn = real_source(tmp_path), synthetic_source(tmp_path)
    md.build_mix(tmp_path / "a", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    md.build_mix(tmp_path / "b", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    md.build_mix(tmp_path / "c", [real], None, 0.1, 0.2, 1.0, 0.2, 0)
    for split in ms.SPLITS:
        first = (tmp_path / "a" / split / "annotations.csv").read_text(encoding="utf-8")
        assert first == (tmp_path / "b" / split / "annotations.csv").read_text(encoding="utf-8")
    for split in ("val", "test"):
        assert (tmp_path / "a" / split / "annotations.csv").read_text(encoding="utf-8") == \
            (tmp_path / "c" / split / "annotations.csv").read_text(encoding="utf-8")


def test_main_prints_no_plate_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real_source(tmp_path)
    synthetic_source(tmp_path)
    assert md.main(["--real", "real1", "--synthetic", "syn", "--output", "mix_cli"]) == 0
    printed = capsys.readouterr().out
    assert "train:" in printed and "test:" in printed
    assert "CAR" not in printed and "MOT" not in printed and "SYN" not in printed
```
```python
# training/ocr/tests/test_evaluate_ocr.py
from __future__ import annotations

import csv
import dataclasses
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import pytest

from ocr_training import evaluate_ocr as ev
from ocr_training.common import TrainingError


def make_split(root: Path, texts: Sequence[str], split: str = "test", prefix: str = "real",
               with_groups: bool = True) -> Path:
    split_dir = root / split
    (split_dir / "images").mkdir(parents=True)
    rows, groups = [], []
    for i, text in enumerate(texts):
        name = f"{prefix}_{i:06d}.png"
        assert cv2.imwrite(str(split_dir / "images" / name), np.full((16, 32, 3), i, np.uint8))
        rows.append((f"images/{name}", text))
        groups.append((f"images/{name}", f"g{i // 2:05d}"))
    for file_name, header, body in (("annotations.csv", ("image_path", "plate_text"), rows),
                                    ("groups.csv", ("image_path", "group_id"), groups)):
        if file_name == "groups.csv" and not with_groups:
            continue
        with (split_dir / file_name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(body)
    return split_dir / "annotations.csv"


def fake_factory(truths: Sequence[str]) -> ev.PredictorFactory:
    def factory(model: Path, config: Path) -> ev.Predictor:
        def predict(images: Sequence[npt.NDArray[np.uint8]]) -> list[str]:
            texts = [truths[int(image[0, 0, 0])] for image in images]
            return texts if model.name == "candidate.onnx" else [t[:-1] for t in texts]
        return predict
    return factory


def metrics(**changes: object) -> ev.ModelMetrics:
    base = ev.ModelMetrics(150, 0.02, 0.9, (0.01, 0.04), {"moto": 0.02, "motocarro": None, "other": 0.02},
                           {"moto": 30, "motocarro": 0, "other": 120})
    return dataclasses.replace(base, **changes)


def test_levenshtein_and_normalize() -> None:
    assert ev.levenshtein("", "ABC") == 3
    assert ev.levenshtein("ABC", "ABD") == 1
    assert ev.levenshtein("ABC123", "ABC12") == 1
    assert ev.normalize_prediction("AB_12") == ""
    assert ev.normalize_prediction("abc123") == ""
    assert ev.normalize_prediction("ABC123") == "ABC123"


def test_compute_metrics() -> None:
    result = ev.compute_metrics(["ABC123", "XYZ98"], ["ABC123", "XYZ98K"], ["g1", "g2"], 0)
    assert result.samples == 2
    assert result.cer == pytest.approx(1 / 12)
    assert result.exact_match_rate == 0.5
    low, high = result.cer_ci95
    assert 0.0 <= low <= result.cer <= high <= 1 / 6 + 1e-12
    assert result.cer_by_category == {"moto": pytest.approx(1 / 6), "motocarro": None, "other": 0.0}
    assert result.samples_by_category == {"moto": 1, "motocarro": 0, "other": 1}
    assert ev.compute_metrics(["ABC123", "XYZ98"], ["ABC123", "XYZ98K"], ["g1", "g2"], 0) == result
    with pytest.raises(TrainingError):
        ev.compute_metrics([], [], [], 0)


def test_decide() -> None:
    baseline = metrics(cer=0.10, exact_match_rate=0.6)
    assert ev.decide(metrics(), baseline) == []
    assert len(ev.decide(metrics(samples=90), baseline)) == 1
    assert len(ev.decide(metrics(cer=0.04), baseline)) == 1
    assert len(ev.decide(metrics(cer_ci95=(0.01, 0.06)), baseline)) == 1
    assert len(ev.decide(metrics(), metrics(cer=0.01, exact_match_rate=0.6))) == 1
    assert len(ev.decide(metrics(), metrics(cer=0.10, exact_match_rate=0.95))) == 1


def test_evaluate_accepts_better_candidate(tmp_path: Path) -> None:
    truths = [f"ABC{i:03d}" for i in range(120)]
    crops = make_split(tmp_path, truths)
    report = ev.evaluate(crops, tmp_path / "candidate.onnx", tmp_path / "base.onnx", tmp_path / "cfg.yaml", 0,
                         fake_factory(truths))
    assert report["accepted"] is True and report["reasons"] == []
    assert report["samples"] == 120
    assert report["candidate"]["cer"] == 0.0
    assert report["baseline"]["cer"] == pytest.approx(1 / 6)
    assert "ABC0" not in json.dumps(report)


def test_evaluate_rejects_small_sample(tmp_path: Path) -> None:
    truths = [f"ABC{i:03d}" for i in range(50)]
    crops = make_split(tmp_path, truths)
    report = ev.evaluate(crops, tmp_path / "candidate.onnx", tmp_path / "base.onnx", tmp_path / "cfg.yaml", 0,
                         fake_factory(truths))
    assert report["accepted"] is False and len(report["reasons"]) == 1


@pytest.mark.parametrize("kwargs", [{"split": "val"}, {"prefix": "syn"}, {"with_groups": False}])
def test_read_split_errors(tmp_path: Path, kwargs: dict[str, object]) -> None:
    crops = make_split(tmp_path, ["ABC123", "ABC124"], **kwargs)  # type: ignore[arg-type]
    with pytest.raises(TrainingError):
        ev.read_split(crops)


def test_write_report(tmp_path: Path) -> None:
    now = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    path = ev.write_report({"accepted": True}, tmp_path / "reports", now)
    assert path.name == "ocr-eval-20260927T100000Z.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"accepted": True}
    with pytest.raises(TrainingError):
        ev.write_report({"accepted": True}, tmp_path / "reports", now)
    with pytest.raises(TrainingError):
        ev.write_report({}, tmp_path / "reports", datetime(2026, 9, 27, 11, 0, 0))
```

## Fuera de alcance
Cambiar `train.py` (p. ej. exponer `--lr`), `chars_to_ocr` (spec 031) o el generador (spec 033); registrar el modelo en
`config/models.yaml` (paso del operador, ADR-014); etiquetar datasets nuevos; validación cruzada por k pliegues.

## Definition of Done
- [ ] En `training/ocr`: `uv run pytest` en verde (incluye los tests de las specs 032 y 033).
- [ ] `uv run python -m ocr_training.synthetic_plates --output syn_v1 --count 1500 --val-fraction 0 --seed 1` y
      `uv run python -m ocr_training.mix_dataset --real ocr_colombia --synthetic syn_v1 --output mix_v1` terminan con
      código 0; `mix_v1/manifest.json` muestra `train_synthetic_fraction` ≤ 0.5 y `moto_target_met: true` (operador).
- [ ] `git status` no muestra `datasets/` ni `runs/`.
- [ ] Ningún módulo nuevo supera 300 líneas ni importa `lector_placas`.
