# 058 - Evaluación con cercanía: ground truth versión 2

> **Estado: bloqueada hasta aprobar el cambio de docs/04.** Cambia la definición de M-02 y M-03 ("placas cercanas").
> Antes de implementarla, un revisor Opus independiente debe aprobar el texto del §3 de docs/04 propuesto aquí y el
> usuario debe confirmarlo (docs/09 §4.5 y §8). Hasta entonces el orquestador no la lanza.

## Objetivo
Que `lector evaluate` mida M-02 y M-03 solo sobre las placas **cercanas** (las que el sistema debe leer tras la spec
057) y que el ground truth admita el modo de cámara en vehículo. El ground truth gana la versión 2: por placa, el ancho
máximo de la placa en píxeles (`max_plate_width_px`); `camera` admite `vehicle_mounted` y `subset` admite `patrol`. La
versión 1 se sigue leyendo y se evalúa como hoy (toda placa legible cuenta).

## Depende de
029, 057, 059.

## Archivos rectores aplicables
- docs/04-evaluacion.md §2 y §3 (el orquestador los actualiza **tras** la aprobación, con el texto del final de esta
  spec), docs/09-enfoque-versatil.md §6 (E6, E7) y D10.
- reglas-seguridad.md SEG-05 (consola y reportes sin texto de placa).

## Archivos a crear/modificar
- `src/lector_placas/evaluation/ground_truth.py`
- `src/lector_placas/evaluation/metrics.py`
- `src/lector_placas/cli/evaluation_commands.py`
- `tests/unit/evaluation/test_ground_truth_v2.py` (nuevo)
- `tests/unit/evaluation/test_metrics_near.py` (nuevo)
- `tests/unit/cli/test_evaluate_near_summary.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `evaluation/ground_truth.py`
- `GroundTruth.version: Literal[1, 2]`; `subset: Literal["street_day", "street_night", "parking", "fast", "patrol"]`;
  `camera: Literal["fixed", "handheld", "vehicle_mounted"]`.
- `GroundTruthPlate` gana `max_plate_width_px: int | None = Field(default=None, ge=1)`.
- `GroundTruth` gana un `model_validator(mode="after")`: con `version == 1`, ninguna placa puede tener
  `max_plate_width_px` (si alguna lo tiene → `ValueError("max_plate_width_px solo existe en la versión 2")`); con
  `version == 2`, toda placa legible debe tenerlo (si no → `ValueError("versión 2: falta max_plate_width_px en una placa legible")`).
  Con versión 1, `patrol` y `vehicle_mounted` se rechazan (`ValueError("patrol y vehicle_mounted exigen la versión 2")`).

### `evaluation/metrics.py`
- `PlateMetrics` gana, **al final** y con valor por defecto: `gt_far_excluded: int = 0`,
  `confirmed_matched_near: int | None = None`, `min_plate_width: int | None = None`.
- `recall_confirmed` pasa a usar `confirmed_matched_near` si no es `None` y `confirmed_matched` en otro caso.
- `compute_metrics(records, truth, tolerance_ms=TOLERANCE_MS, min_plate_width: int | None = None)`.

## Comportamiento esperado
1. **Placas cercanas.** Si `min_plate_width is None` o `truth.version == 1`: todas las legibles son cercanas. Si no, una
   legible es cercana si `max_plate_width_px >= min_plate_width`.
2. **`compute_metrics`** (con `legibles` = placas legibles y `cercanas` ⊆ `legibles`):
   - `gt_legible = len(cercanas)`; `gt_far_excluded = len(legibles) - len(cercanas)`;
   - `confirmed_matched = greedy_match(records, legibles, CONFIRMED_ONLY, tol)` (M-01 sigue contra **todas** las
     legibles: una confirmada correcta de una placa lejana no es un error);
   - `confirmed_matched_near = greedy_match(records, cercanas, CONFIRMED_ONLY, tol)`;
   - `any_matched = greedy_match(records, cercanas, ANY_STATUS, tol)`;
   - `confirmed_total`, `corrected_total`: sin cambios; `min_plate_width` = el argumento (o `None` con versión 1).
   - `greedy_match` no cambia: ya filtra por `legible`; se le pasa la lista ya filtrada.
3. **`cmd_evaluate`.** Tras ejecutar la corrida, si `truth.version == 2`:
   `w, h = repository.run_frame_sizes()[result.run_id]`; `_, profile = config.profile(args.profile)`;
   `min_plate_width = effective_min_width(w, h, profile.min_plate_width_px, profile.near_min_width_frac)`
   (de `application/proximity.py`); si no, `None`. Se pasa a `compute_metrics`.
4. **Reporte.** `_video_payload` añade al final las claves `"gt_far_excluded"`, `"confirmed_matched_near"` y
   `"min_plate_width"` con esos valores.
5. **Consola.** `_write_video_summary` añade, justo antes de `speed_factor=`, el texto
   `f"gt_far_excluded={metrics.gt_far_excluded} min_plate_width={'n/d' if metrics.min_plate_width is None else metrics.min_plate_width} "`.

## Casos borde y manejo de errores
- Versión 1: resultados idénticos a los actuales (`gt_far_excluded == 0`, `min_plate_width == None`).
- Todas las placas lejanas: `gt_legible == 0` y M-02/M-03 son `None` (sin denominador), como hoy.

## Tests de aceptación (en prosa)
`tests/unit/evaluation/test_ground_truth_v2.py` (JSON sintéticos en `tmp_path`):
- `test_v1_still_loads`: el ejemplo de docs/04 §2 (versión 1) carga y sus placas tienen `max_plate_width_px is None`.
- `test_v2_requires_width_on_legible`: versión 2 con una placa legible sin `max_plate_width_px` → `EvaluationError`;
  con `max_plate_width_px: 60` en las legibles y sin él en la ilegible, carga.
- `test_v1_rejects_v2_fields`: versión 1 con `max_plate_width_px` → `EvaluationError`; versión 1 con
  `camera: "vehicle_mounted"` o `subset: "patrol"` → `EvaluationError`; versión 2 con ambos, carga.
- `test_width_must_be_positive`: `max_plate_width_px: 0` → `EvaluationError`.

`tests/unit/evaluation/test_metrics_near.py` (registros `SightingRecord` sintéticos):
GT versión 2 con tres legibles: `ABC123` (0–1000 ms, ancho 60), `DEF456` (2000–3000 ms, ancho 40),
`GHI789` (4000–5000 ms, ancho 50), y avistamientos confirmados `ABC123` (0–900) y `DEF456` (2100–2900) y uno
`unverified` `GHI789` (4100–4900).
- `test_near_filter`: con `min_plate_width=48`: `gt_legible == 2`, `gt_far_excluded == 1`, `confirmed_matched == 2`,
  `confirmed_matched_near == 1`, `any_matched == 2`, `precision_confirmed == 1.0`, `recall_any == 1.0`,
  `recall_confirmed == 0.5`, `min_plate_width == 48`.
- `test_without_min_width`: con `min_plate_width=None`: `gt_legible == 3`, `gt_far_excluded == 0`,
  `recall_any == 1.0`, `recall_confirmed == pytest.approx(2 / 3)`.
- `test_v1_ignores_min_width`: el mismo caso como versión 1 (sin anchos) con `min_plate_width=48` da lo mismo que
  `test_without_min_width` y `min_plate_width is None`.
- `test_old_constructor_still_works`: `PlateMetrics(3, 2, 2, 3, 0).recall_confirmed == pytest.approx(2 / 3)`.

`tests/unit/cli/test_evaluate_near_summary.py`:
- `test_summary_line`: `_write_video_summary` con `PlateMetrics(2, 2, 2, 2, 0, gt_far_excluded=1,
  confirmed_matched_near=1, min_plate_width=48)`, `speed_factor=1.5`, `peak_mib=None` y `"r.json"` escribe una primera
  línea que contiene `gt_far_excluded=1 min_plate_width=48 speed_factor=` y ninguna placa.

## Texto propuesto para docs/04 §3 (lo aplica el orquestador tras la aprobación)
- M-02: "Placas GT legibles **cercanas** emparejadas con algún avistamiento (`confirmed` o `unverified`) de igual texto /
  placas GT legibles cercanas." M-03: igual con `confirmed`. M-01 no cambia.
- "Cercana (ground truth versión 2): `max_plate_width_px` ≥ ancho mínimo efectivo del perfil usado en la corrida,
  `ceil(max(min_plate_width_px, near_min_width_frac × lado mayor del frame))` (ADR-017). Con ground truth versión 1,
  todas las legibles son cercanas."
- §2: formato versión 2 (`max_plate_width_px` por placa legible, medido como el ancho en píxeles de la placa en el frame
  donde se ve más grande; `camera` añade `vehicle_mounted`; `subset` añade `patrol`). Desglose del reporte por `camera`.

## Fuera de alcance
- Anotar videos (operador). Cambiar las metas numéricas de M-01..M-03.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde, sin modificar tests existentes.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
