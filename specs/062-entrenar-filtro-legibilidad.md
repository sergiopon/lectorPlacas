# 062 - Entrenamiento del filtro de legibilidad (`training/legibility`)

## Objetivo
Crear el proyecto de entrenamiento `training/legibility` (uv independiente, solo numpy) que, a partir de una exportación
de `lector dataset export-legibility` (specs 055 y 059), entrena una **regresión logística multinomial** de tres clases
(`legible`, `borrosa`, `no_placa`) sobre la **población cercana** revisada por humanos, la evalúa **dejando fuera un
video cada vez**, elige el umbral y escribe el modelo (JSON) y un informe con las condiciones de aceptación. No decide
si se adopta: eso lo hace un revisor Opus con el informe (docs/09 §4.2).

## Depende de
055, 059. No depende de código de `src/` (proyecto separado).

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §4.2 (población, criterio, mínimo de datos, línea base), docs/08 §2.4.
- reglas-seguridad.md SEG-04 (salidas 0700/0600), SEG-05 (sin texto de placa: el dataset no lo trae), SEG-09/10
  (tests con datos sintéticos; los datos reales no salen del equipo), SEG-11 (`datasets/` y `runs/` ignorados).
- CLAUDE.md: los proyectos de `training/` se ejecutan desde su carpeta (`uv sync`, `uv run pytest`).

## Archivos a crear/modificar
- `training/legibility/pyproject.toml` (nuevo) y `training/legibility/uv.lock` (lo genera `uv lock`)
- `training/legibility/legibility_training/__init__.py` (vacío)
- `training/legibility/legibility_training/common.py`
- `training/legibility/legibility_training/dataset.py`
- `training/legibility/legibility_training/features.py`
- `training/legibility/legibility_training/model.py`
- `training/legibility/legibility_training/evaluate.py`
- `training/legibility/legibility_training/train.py` (punto de entrada)
- `training/legibility/tests/__init__.py` (vacío)
- `training/legibility/tests/test_features.py`
- `training/legibility/tests/test_dataset.py`
- `training/legibility/tests/test_model.py`
- `training/legibility/tests/test_train.py`

## Dependencias externas
`pyproject.toml` (copia la forma de `training/ocr/pyproject.toml`):
- `[project]`: `name = "lector-placas-training-legibility"`, `version = "0.1.0"`, `requires-python = "==3.13.*"`,
  `dependencies = ["numpy==2.5.3"]` (misma versión que la raíz).
- `[dependency-groups] dev = ["pytest==9.1.1"]`; `[tool.uv] package = false`;
  `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`.
- `uv lock` y `uv sync --locked` **desde `training/legibility`**.

## Interfaces y tipos involucrados

### `common.py`
`TRAINING_DIR = Path(__file__).resolve().parents[1]`; `DATASETS_DIR = TRAINING_DIR / "datasets"`;
`RUNS_DIR = TRAINING_DIR / "runs"`; `class LegibilityError(Exception)`;
`CLASSES: Final[tuple[str, str, str]] = ("legible", "borrosa", "no_placa")`;
`REASONS: Final[tuple[str, ...]] = ("insufficient_readings", "low_confidence", "low_agreement", "unrecognized_format", "unverified_format", "vehicle_format_mismatch", "ambiguous_format", "correction_conflict")`;
`MIN_PLATE_WIDTH_PX: Final[int] = 32`; `NEAR_MIN_WIDTH_FRAC: Final[float] = 0.025`;
`MIN_PER_CLASS: Final[int] = 100`; `MIN_VIDEO_GROUPS: Final[int] = 4`; `MAX_HIDDEN_LEGIBLE: Final[float] = 0.05`;
`BOOTSTRAP_ROUNDS: Final[int] = 2000`.

### `features.py`
- `FEATURE_NAMES: Final[tuple[str, ...]]` con 16 nombres, en este orden: `confidence`, `agreement`, `log_num_readings`,
  `relative_width`, `aspect`, `log_sharpness`, `contrast`, `is_motorcycle`, y `reason_<r>` por cada `r` de `REASONS`.
- `def feature_vector(row: Row) -> np.ndarray` (float64, longitud 16).

### `dataset.py`
- `@dataclass(frozen=True, slots=True) class Row` con `label: str`, `human_reviewed: bool`, `video_group: int`,
  `vehicle_type: str`, `confidence: float`, `agreement: float`, `num_readings: int`, `reasons: tuple[str, ...]`,
  `plate_width_px: int | None`, `plate_height_px: int | None`, `sharpness: float | None`, `contrast: float | None`,
  `frame_width: int | None`, `frame_height: int | None`.
- `def read_export(export_dir: Path) -> list[Row]`.
- `def near_population(rows: Sequence[Row]) -> list[Row]`.

### `model.py`
- `@dataclass(frozen=True, slots=True) class LogisticModel` con `mean: np.ndarray` (16), `std: np.ndarray` (16),
  `weights: np.ndarray` (3×16), `bias: np.ndarray` (3).
- `def fit(x: np.ndarray, y: np.ndarray) -> LogisticModel` (`x` N×16, `y` enteros 0–2).
- `def predict_proba(model: LogisticModel, x: np.ndarray) -> np.ndarray` (N×3).
- Constantes: `L2: Final[float] = 1.0`, `LEARNING_RATE: Final[float] = 0.1`, `ITERATIONS: Final[int] = 2000`.

### `evaluate.py`
- `def leave_one_video_out(rows: Sequence[Row]) -> np.ndarray`: probabilidades fuera de muestra (N×3), en el orden de
  `rows`.
- `def choose_threshold(p_legible: np.ndarray, is_legible: np.ndarray) -> float`.
- `def rates(p_legible, is_legible, threshold) -> tuple[float, float]`: `(legibles_ocultas, inservibles_ocultas)`.
- `def baseline_rates(rows) -> tuple[float, float]`.
- `def bootstrap_upper(p_legible, is_legible, groups, threshold, seed) -> float`.

### `train.py`
`python -m legibility_training.train --export <dir> --name <nombre> [--seed 0]`.

## Comportamiento esperado

### 1. Lectura (`read_export`)
- `export_dir` se resuelve; debe estar dentro de `DATASETS_DIR` (como `training/ocr`), ser un directorio y contener
  `annotations.csv`; si no → `LegibilityError("exportación no válida")`.
- El CSV debe tener exactamente las 20 columnas de la exportación (spec 055 + 059); si no →
  `LegibilityError("columnas inesperadas")`.
- Por fila: `human_reviewed` `"1"`/`"0"`; enteros y flotantes con `int()`/`float()`; celda vacía → `None`; `reasons`
  vacía → `()`, si no `tuple(celda.split("|"))`. Un valor que no se pueda convertir → `LegibilityError("fila inválida: <n>")`
  con `n` el número de fila de datos empezando en 1. No se leen las imágenes.

### 2. Población (`near_population`)
Conserva, en orden, las filas que cumplen **todo**: `human_reviewed` verdadero; `plate_width_px`, `plate_height_px`,
`sharpness`, `contrast`, `frame_width` y `frame_height` no nulos; y
`plate_width_px >= math.ceil(round(max(MIN_PLATE_WIDTH_PX, NEAR_MIN_WIDTH_FRAC * max(frame_width, frame_height)), 6))`.

### 3. Características (`feature_vector`), en el orden de `FEATURE_NAMES`
`confidence`; `agreement`; `math.log(num_readings)`; `plate_width_px / max(frame_width, frame_height)`;
`plate_height_px / plate_width_px`; `math.log1p(sharpness)`; `contrast / 128.0`;
`1.0 if vehicle_type == "motorcycle" else 0.0`; y, por cada `r` de `REASONS`, `1.0 if r in reasons else 0.0`. Las razones
que no están en `REASONS` (por ejemplo `predicted_illegible`) se ignoran. Requiere los campos no nulos (la población ya
lo garantiza; si no → `LegibilityError("fila sin medidas")`).

### 4. Modelo (`fit`)
1. `mean = x.mean(axis=0)`; `std = x.std(axis=0)`; donde `std == 0.0`, `std = 1.0`; `z = (x - mean) / std`.
2. `W = zeros(3, 16)`, `b = zeros(3)`, `Y` = one-hot de `y` (N×3).
3. `ITERATIONS` veces: `logits = z @ W.T + b`; `P = softmax(logits)` por filas (restando el máximo de cada fila);
   `G = (P - Y) / N`; `W -= LEARNING_RATE * (G.T @ z + L2 * W / N)`; `b -= LEARNING_RATE * G.sum(axis=0)`.
4. `predict_proba`: `softmax(((x - mean) / std) @ W.T + b)`.

### 5. Evaluación
1. `leave_one_video_out`: para cada `video_group` distinto (orden ascendente), entrena `fit` con las filas de los otros
   grupos y predice las del grupo; ensambla N×3 en el orden de `rows`.
2. `choose_threshold`: candidatos `t = k / 100` para `k` de 0 a 99; devuelve el **mayor** `t` cuya fracción de legibles
   con `p_legible < t` es `<= MAX_HIDDEN_LEGIBLE` (con `t = 0` no se oculta nada, así que siempre hay uno).
3. `rates`: legibles ocultas = legibles con `p_legible < t` / legibles; inservibles ocultas = (borrosas + no_placa) con
   `p_legible < t` / (borrosas + no_placa).
4. `baseline_rates`: las mismas dos fracciones con la regla "oculta si `num_readings <= 1`".
5. `bootstrap_upper`: con `numpy.random.default_rng(seed)`, `BOOTSTRAP_ROUNDS` remuestreos con reemplazo de los
   **grupos de video** (tantos como grupos hay); en cada uno, la fracción de legibles ocultas con el umbral dado sobre
   las filas de los grupos elegidos (repetidas según se elijan); devuelve el percentil 97,5 (`np.percentile(…, 97.5)`).
   Remuestreos sin legibles no cuentan.

### 6. `train.py`, en este orden
1. `rows = near_population(read_export(DATASETS_DIR / args.export))`.
2. Si alguna clase tiene menos de `MIN_PER_CLASS` filas o hay menos de `MIN_VIDEO_GROUPS` grupos de video →
   `LegibilityError(f"datos insuficientes: legible={a} borrosa={b} no_placa={c} grupos={g}")` y código de salida 1.
3. `oof = leave_one_video_out(rows)`; `t = choose_threshold(oof[:, 0], es_legible)`;
   `(l, i) = rates(...)`; `(bl, bi) = baseline_rates(rows)`; `upper = bootstrap_upper(..., seed=args.seed)`.
4. `final = fit` con **todas** las filas.
5. Carpeta de salida `RUNS_DIR / args.name / <UTC %Y-%m-%d_%H-%M-%S>` (0700; `args.name` debe cumplir
   `^[a-z0-9_]{1,40}$`, si no `LegibilityError("nombre inválido")`). Escribe con 0600:
   - `model.json`: `{"version": 1, "features": [...16], "classes": ["legible", "borrosa", "no_placa"], "mean": [...],
     "std": [...], "weights": [[...16] x 3], "bias": [...3], "threshold": t}` (flotantes de Python, sin redondear).
   - `report.json`: `{"n": {"legible": a, "borrosa": b, "no_placa": c}, "video_groups": g, "threshold": t,
     "hidden_legible": l, "hidden_legible_upper95": upper, "hidden_unusable": i, "baseline_hidden_legible": bl,
     "baseline_hidden_unusable": bi, "conditions": {"c1_hidden_legible_le_5pct": l <= 0.05,
     "c2_upper95_le_8pct": upper <= 0.08, "c3_hidden_unusable_ge_60pct": i >= 0.60,
     "c4_beats_baseline": i > bi and l <= max(bl, 0.05)}, "verdict": "ACEPTAR" si las cuatro son verdaderas, si no "RECHAZAR"}`.
6. Imprime por consola, en líneas: los conteos, el umbral, las cuatro condiciones con `OK`/`NO`, el veredicto y la ruta
   de la carpeta. Código de salida 0 (también con `RECHAZAR`).

## Casos borde y manejo de errores
- Un grupo de video con una sola clase: se entrena y predice igual (la regresión lo admite).
- `--export` fuera de `datasets/` (p. ej. con `..`) → `LegibilityError("exportación no válida")`.
- Nada de lo que se imprime o escribe contiene texto de placa (la exportación no lo trae).

## Tests de aceptación (en prosa)
Datos sintéticos generados en el test (filas y CSV inventados; sin imágenes reales). Ejecutar desde `training/legibility`.

`tests/test_features.py`:
- `test_feature_vector_reference`: la fila `confidence=0.8, agreement=0.75, num_readings=4, plate_width_px=60,
  plate_height_px=20, frame_width=1920, frame_height=1080, sharpness=99.0, contrast=64.0, vehicle_type="car",
  reasons=("low_confidence",)` da exactamente (con `pytest.approx`)
  `[0.8, 0.75, 1.3862943611198906, 0.03125, 0.3333333333333333, 4.605170185988092, 0.5, 0.0, 0, 1, 0, 0, 0, 0, 0, 0]`.
  **Este mismo vector de referencia lo usa la spec 063: no cambiarlo.**
- `test_unknown_reasons_ignored_and_motorcycle`: con `vehicle_type="motorcycle"` y
  `reasons=("predicted_illegible", "correction_conflict")`, la posición 8 vale 1.0, la última 1.0 y ninguna otra razón.

`tests/test_dataset.py` (escribe un CSV con las 20 columnas en `tmp_path` y parchea `DATASETS_DIR`):
- `test_read_export_parses_rows`: dos filas (una con celdas de calidad vacías) dan `Row` con `None` en esas celdas y
  `reasons` como tupla.
- `test_read_export_rejects_bad_input`: columnas distintas → `columnas inesperadas`; un `confidence` `"x"` en la fila 2 →
  `fila inválida: 2`; una ruta fuera de `DATASETS_DIR` → `exportación no válida`.
- `test_near_population`: con frame 1920×1080 (mínimo 48), anchos 47 y 48 → solo queda el de 48; con frame 1280×720
  (mínimo 32), ancho 32 queda; una fila con `human_reviewed` falso o con `sharpness` vacía se descarta.

`tests/test_model.py`:
- `test_fit_separates_classes`: 300 filas sintéticas (100 por clase, `numpy.random.default_rng(0)`) donde la primera
  característica es 0,9 ± 0,05 para `legible`, 0,3 ± 0,05 para `borrosa` y 0,1 ± 0,05 para `no_placa` y el resto ruido;
  `predict_proba` acierta la clase de mayor probabilidad en ≥ 95 % de las filas y cada fila suma 1 (tolerancia 1e-9).
- `test_constant_feature_has_unit_std`: una columna constante produce `std == 1.0` en esa posición.
- `test_fit_is_deterministic`: dos llamadas con los mismos datos dan pesos idénticos (`np.array_equal`).

`tests/test_train.py`:
- `test_choose_threshold`: 20 legibles con `p_legible = [0.505, 0.515] + [0.9] * 18` (todas `is_legible` verdadero):
  con `t = 0.51` se oculta 1 de 20 (5 %) y con `t = 0.52`, 2 de 20; devuelve `0.51`.
- `test_rates_and_baseline`: `rates([0.2, 0.8, 0.3, 0.9], [True, True, False, False], 0.5)` es `(0.5, 0.5)`; filas con
  `num_readings` `[1, 3, 1, 5]` y clases `[legible, legible, borrosa, no_placa]` dan `baseline_rates == (0.5, 0.5)`.
- `test_bootstrap_upper_deterministic`: misma semilla → mismo valor; resultado en [0, 1].
- `test_train_end_to_end`: un CSV sintético con 5 grupos de video y 120 filas por clase, separable como en
  `test_fit_separates_classes`; `main(["--export", "<rel>", "--name", "prueba"])` devuelve 0 y crea `model.json` y
  `report.json` (0600) en una carpeta 0700 bajo `RUNS_DIR/prueba/` (con `RUNS_DIR` parcheado a `tmp_path`); `model.json`
  tiene 16 `features`, `weights` de 3×16 y `threshold` en [0, 0.99]; `report.json` tiene las cuatro condiciones.
- `test_train_insufficient_data`: con 99 filas de `no_placa` devuelve 1 y el mensaje empieza por `datos insuficientes:`.

## Fuera de alcance
- Usar el modelo en el pipeline (spec 063). Una CNN sobre el recorte: solo si este modelo se rechaza, en otra spec.
- Decidir la aceptación: revisor Opus con `report.json` (docs/09 §4.2).

## Definition of Done (desde `training/legibility`)
- [ ] `uv lock` y `uv sync --locked` sin errores.
- [ ] `uv run pytest -q` en verde.
