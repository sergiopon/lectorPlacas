# 063 - Filtro de legibilidad en el pipeline (`PREDICTED_ILLEGIBLE` / `PREDICTED_NOT_PLATE`)

## Objetivo
Aplicar en `ProcessVideo`, al guardar cada avistamiento, el modelo de legibilidad entrenado por la spec 062 (coeficientes
copiados a `config/lector.yaml`). Si la probabilidad de "legible" queda por debajo del umbral, el avistamiento queda
`unverified` con una razón nueva: `predicted_not_plate` o `predicted_illegible`. Nunca se borra nada. Con
`legibility.enabled: false` (valor del repo hasta que un revisor Opus acepte un modelo) no cambia nada.

## Depende de
057, 059, 062.

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §1.5 y §4.2; docs/08 §2 (D3). ADR-007 (consolidación sin cambios).
- reglas-seguridad.md SEG-05 (sin texto de placa en logs).

## Archivos a crear/modificar
- `src/lector_placas/domain/entities.py` (`UnverifiedReason`: dos valores nuevos al final)
- `src/lector_placas/application/legibility.py` (nuevo)
- `src/lector_placas/application/process_video.py`
- `src/lector_placas/infrastructure/config.py` (`LegibilityConfig`, `AppConfig.legibility`)
- `src/lector_placas/cli/composition.py` (`build_legibility_model`; `build_process_video`)
- `src/lector_placas/gui/labels.py` (textos de las dos razones nuevas)
- `config/lector.yaml`
- `tests/unit/application/test_legibility.py` (nuevo)
- `tests/unit/application/test_process_video_legibility.py` (nuevo)
- `tests/unit/infrastructure/test_config.py` (un test nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `domain/entities.py`
`UnverifiedReason` añade, **después** de `CORRECTION_CONFLICT` y en este orden:
`PREDICTED_ILLEGIBLE = "predicted_illegible"` y `PREDICTED_NOT_PLATE = "predicted_not_plate"`.

### `application/legibility.py` (stdlib, numpy y `domain`)
- `FEATURE_COUNT: Final[int] = 16`.
- `REASON_FEATURES: Final[tuple[UnverifiedReason, ...]]` = los 8 primeros miembros de `UnverifiedReason`, en orden
  (de `INSUFFICIENT_READINGS` a `CORRECTION_CONFLICT`).
- `@dataclass(frozen=True, slots=True) class LegibilityModel` con `mean: tuple[float, ...]`, `std: tuple[float, ...]`,
  `weights: tuple[tuple[float, ...], ...]`, `bias: tuple[float, ...]`, `threshold: float`. `__post_init__`: longitudes
  16, 16, 3×16 y 3, todos los `std > 0` y `0 <= threshold < 1`; si no, `InvalidEntityError("modelo de legibilidad inválido")`.
- `def feature_vector(plate: ConsolidatedPlate, quality: CropQuality, frame_width: int, frame_height: int, vehicle_type: VehicleType) -> tuple[float, ...]`.
- `def predict(model: LegibilityModel, features: Sequence[float]) -> tuple[float, float, float]`.
- `def legibility_reason(model: LegibilityModel, features: Sequence[float]) -> UnverifiedReason | None`.

### `application/process_video.py`
- `ProcessingSettings` gana, **al final**, `legibility: LegibilityModel | None = None`.
- `_Counters` gana `frame_width: int = 0` y `frame_height: int = 0`, que `_run` rellena con `info.width` e
  `info.height` antes de procesar frames.

### `infrastructure/config.py`
`class LegibilityConfig(StrictModel)` con `enabled: bool`, `threshold: float | None = None`,
`mean: tuple[float, ...] | None = None`, `std: tuple[float, ...] | None = None`,
`weights: tuple[tuple[float, ...], ...] | None = None`, `bias: tuple[float, ...] | None = None`, y un
`model_validator(mode="after")` (comportamiento 4). `AppConfig` gana `legibility: LegibilityConfig` (obligatorio),
después de `retention`.

### `cli/composition.py`
`def build_legibility_model(config: AppConfig) -> LegibilityModel | None`: `None` si `not config.legibility.enabled`;
si no, `LegibilityModel(mean, std, weights, bias, threshold)` con los valores de la configuración. `build_process_video`
usa `dataclasses.replace(build_processing_settings(name, profile), legibility=build_legibility_model(config))`.

## Comportamiento esperado

### 1. `feature_vector` (idéntico a la spec 062 §3; el vector de referencia de ambas specs es el mismo)
En este orden: `plate.confidence`; `plate.agreement`; `math.log(plate.num_readings)`;
`quality.plate_width_px / max(frame_width, frame_height)`; `quality.plate_height_px / quality.plate_width_px`;
`math.log1p(quality.sharpness)`; `quality.contrast / 128.0`; `1.0 if vehicle_type is VehicleType.MOTORCYCLE else 0.0`;
y, por cada `r` de `REASON_FEATURES`, `1.0 if r in plate.reasons else 0.0`.

### 2. `predict` y `legibility_reason`
- `predict`: `z[j] = (features[j] - mean[j]) / std[j]`; `logit[c] = sum_j weights[c][j] * z[j] + bias[c]`;
  softmax restando el máximo; devuelve `(p_legible, p_borrosa, p_no_placa)`.
- `legibility_reason`: `p = predict(...)`; si `p[0] >= threshold` → `None`; si no, `PREDICTED_NOT_PLATE` si
  `p[2] > p[1]`, y `PREDICTED_ILLEGIBLE` en otro caso (empate incluido).

### 3. `ProcessVideo._save_track`
Después de consolidar y de calcular `quality` (spec 059), y **antes** de crear el `Sighting`:
si `settings.legibility is not None` y `quality is not None`:
`reason = legibility_reason(settings.legibility, feature_vector(plate, quality, counters.frame_width, counters.frame_height, track.vehicle_type))`;
si `reason is not None`: `plate = dataclasses.replace(plate, status=ReviewStatus.UNVERIFIED, reasons=plate.reasons + (reason,))`.
Los contadores de confirmados/sin confirmar, el log del avistamiento y el `DuplicateCandidate` (spec 061) usan el
`plate` ya modificado. Si `quality` es `None` (sin recorte), el filtro no se aplica.

### 4. Validación de `LegibilityConfig`
Si `enabled` es `False`, el resto se ignora. Si es `True`:
1. Si alguno de `threshold`, `mean`, `std`, `weights`, `bias` es `None` →
   `ValueError("legibility.enabled exige threshold, mean, std, weights y bias")`.
2. Si `len(mean) != 16`, `len(std) != 16`, `len(weights) != 3`, alguna fila de `weights` no tiene 16 valores o
   `len(bias) != 3` → `ValueError("legibility: dimensiones inválidas (se esperan 16 características y 3 clases)")`.
3. Si algún `std <= 0` → `ValueError("legibility: std debe ser > 0")`.
4. Si no `0 <= threshold < 1` → `ValueError("legibility: threshold debe estar en [0, 1)")`.

### 5. Configuración y GUI
- `config/lector.yaml`: sección nueva, después de `retention`, exactamente `legibility:` con `enabled: false` y un
  comentario `# spec 063: copiar threshold, mean, std, weights y bias de model.json (spec 062) cuando un revisor Opus lo acepte`.
- `gui/labels.py`: `REASON_TEXTS` añade `PREDICTED_ILLEGIBLE: "Parece borrosa (filtro automático)"` y
  `PREDICTED_NOT_PLATE: "Parece que no es una placa (filtro automático)"`.

## Casos borde y manejo de errores
- Un avistamiento confirmado por el consolidador que el filtro marca pasa a `unverified` (CONFIRMED no admite razones);
  queda para revisión y la vista por defecto lo oculta (spec 064).
- `UnverifiedReason` crece: la BD guarda las razones como texto (sin migración), igual que en la spec 050.

## Tests de aceptación (en prosa)
`tests/unit/application/test_legibility.py`:
- `test_feature_vector_reference`: `ConsolidatedPlate("ABC123", 0.8, 0.75, 4, UNVERIFIED, (LOW_CONFIDENCE,), ())`,
  `CropQuality(60, 20, 99.0, 64.0)`, frame 1920×1080, `CAR` → exactamente (con `pytest.approx`)
  `[0.8, 0.75, 1.3862943611198906, 0.03125, 0.3333333333333333, 4.605170185988092, 0.5, 0.0, 0, 1, 0, 0, 0, 0, 0, 0]`
  (el mismo vector que la spec 062).
- `test_predicted_reasons_are_not_features`: un `plate` con razones `(LOW_CONFIDENCE, PREDICTED_ILLEGIBLE)` da el mismo
  vector que con `(LOW_CONFIDENCE,)`.
- `test_predict_uniform`: modelo con `mean` 0, `std` 1, `weights` 0 y `bias (0, 0, 0)` → `(1/3, 1/3, 1/3)` (approx).
- `test_legibility_reason` (umbral 0,5): `bias (0, 0, 0)` → `PREDICTED_ILLEGIBLE` (empate); `bias (0, 0, 1)` →
  `PREDICTED_NOT_PLATE`; `bias (0, 1, 0)` → `PREDICTED_ILLEGIBLE`; `bias (5, 0, 0)` → `None`.
- `test_invalid_model`: `mean` de 15 valores, un `std` 0 y `threshold` 1.0 lanzan `InvalidEntityError`.

`tests/unit/application/test_process_video_legibility.py` (reutiliza `FakeSource`, `FakeSourceFactory`,
`ScriptedVehicleDetector`, `SingleTrackTracker`, `FixedPlateDetector`, `CyclingReader`, `ConstantQuality` y `SHA` de
`tests.unit.application.test_process_video`, con un `build` propio que acepta `legibility`):
- `test_filter_marks_confirmed_as_not_plate`: 10 frames, lector `CyclingReader(["ABC123"])`, modelo con pesos 0,
  `bias (0, 0, 1)` y umbral 0,5: el avistamiento queda `UNVERIFIED` con `reasons == (PREDICTED_NOT_PLATE,)` y
  `stats.sightings_unverified == 1`.
- `test_filter_keeps_legible`: igual con `bias (5, 0, 0)`: queda `CONFIRMED` sin razones.
- `test_no_model_no_change`: sin modelo, queda `CONFIRMED` (como el test existente `test_happy_path_confirms_plate`).

`tests/unit/infrastructure/test_config.py` (añadir):
- `test_legibility_disabled_by_default`: `load_config(REAL).legibility.enabled is False` y
  `composition.build_legibility_model(config) is None`.
- `test_legibility_validation` (parametrizado sobre `base_data()`): `enabled: true` sin más claves → contiene
  `legibility.enabled exige threshold, mean, std, weights y bias`; con `mean` de 15 valores → contiene
  `dimensiones inválidas`; con un `std` 0 → contiene `std debe ser > 0`; con `threshold` 1.0 → contiene
  `threshold debe estar en [0, 1)`; un caso válido (16/16/3×16/3, `std` 1, `threshold` 0.4) carga y
  `build_legibility_model` devuelve un `LegibilityModel` con `threshold == 0.4`.

## Fuera de alcance
- Ocultar en las vistas y medir las ocultas (spec 064). Encender el filtro: paso del operador tras la aceptación del
  revisor Opus (copiar los valores de `model.json` a `config/lector.yaml` y poner `enabled: true`).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
