# 064 - Vista "solo legibles": filtro de baja calidad en el navegador y métricas de lo oculto

## Objetivo
Permitir consultar los avistamientos excluyendo, o mostrando solo, los marcados por el filtro de legibilidad
(razones `predicted_*`, spec 063), y medir en `evaluate-review` cuántos de los ocultos eran legibles. La web (spec 066)
usará por defecto "excluir"; la GUI PySide6 no cambia (sigue viéndolo todo) porque se retira en la spec 073.

## Depende de
038, 041, 061, 063.

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §1.5; docs/08 §2.3–§2.4 y §6 (decisión 5: lo oculto en una pestaña aparte).
- reglas-seguridad.md SEG-15 (SQL literal y parametrizado).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py` (`SightingQuery.low_quality`)
- `src/lector_placas/adapters/persistence/sqlcipher_browser.py`
- `src/lector_placas/evaluation/review_metrics.py`
- `src/lector_placas/cli/review_evaluation_commands.py`
- `tests/fixtures/fakes.py`
- `tests/unit/application/test_low_quality_query.py` (nuevo)
- `tests/integration/test_low_quality_filter.py` (nuevo)
- `tests/unit/evaluation/test_review_metrics_hidden.py` (nuevo)
- `tests/unit/cli/test_review_evaluation_hidden.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
- `ports.py`: `LowQualityFilter: TypeAlias = Literal["include", "exclude", "only"]`; `SightingQuery` gana, **al final**,
  `low_quality: LowQualityFilter = "include"`. `__post_init__` añade: si no está en esos tres valores →
  `InvalidEntityError("low_quality inválido")`.
- `review_metrics.py`: `ReviewMetrics` gana, **al final** y con valor por defecto `0`, `hidden_total: int`,
  `hidden_legible: int`, `hidden_unusable: int`, `hidden_pending: int`. Constante
  `PREDICTED_REASONS: Final[frozenset[UnverifiedReason]] = frozenset({UnverifiedReason.PREDICTED_ILLEGIBLE, UnverifiedReason.PREDICTED_NOT_PLATE})`.

## Comportamiento esperado
1. **Navegador SQLCipher.** `_SEARCH_SQL` y `_COUNT_SQL` añaden, después de la condición de duplicados (spec 061),
   `AND (? = 'include' OR (? = 'exclude' AND instr(reasons, 'predicted_') = 0) OR (? = 'only' AND instr(reasons, 'predicted_') > 0))`;
   `_filter_params` añade al final tres veces `query.low_quality`.
2. **Fake.** `_matches` añade: con `"exclude"`, ninguna razón cuyo `.value` empiece por `"predicted_"`; con `"only"`,
   al menos una; con `"include"`, sin condición.
3. **Métricas.** `compute_review_metrics` calcula, sobre los registros con alguna razón de `PREDICTED_REASONS`
   (`ocultos`): `hidden_total = len(ocultos)`; `hidden_legible` = ocultos con `reviewed_at` no nulo y estado `CONFIRMED`
   o `CORRECTED`; `hidden_unusable` = ocultos con estado `REJECTED` o `ILLEGIBLE`; `hidden_pending` = ocultos con estado
   `UNVERIFIED`. Las demás métricas no cambian.
4. **`evaluate-review`.** `_write_summary` escribe, **entre** la línea de métricas actual y la de `reporte=`, la línea
   `f"ocultas={m.hidden_total} ocultas_legibles={m.hidden_legible} ocultas_inservibles={m.hidden_unusable} ocultas_pendientes={m.hidden_pending}\n"`.
   El JSON del reporte incluye los cuatro campos (sale de `dataclasses.asdict`, sin cambios de código ahí).

## Casos borde y manejo de errores
- `SightingQuery()` sin argumentos sigue devolviendo lo mismo que antes de esta spec (salvo duplicados, spec 061).
- Los ocultos siguen en exportaciones, revisión por CLI y métricas generales.

## Tests de aceptación (en prosa)
Avistamientos sintéticos: A sin razones (`CONFIRMED`), B `UNVERIFIED` con `(LOW_CONFIDENCE,)`, C `UNVERIFIED` con
`(PREDICTED_ILLEGIBLE,)`, D `UNVERIFIED` con `(LOW_CONFIDENCE, PREDICTED_NOT_PLATE)`.

`tests/unit/application/test_low_quality_query.py` (fake):
- `test_default_includes_everything`: `search_sightings(SightingQuery(), 10, 0)` devuelve A, B, C y D.
- `test_exclude_and_only`: `low_quality="exclude"` → A y B (y `count_sightings` 2); `"only"` → C y D (2).
- `test_invalid_value`: `SightingQuery(low_quality="otro")` lanza `InvalidEntityError`.

`tests/integration/test_low_quality_filter.py` (SQLCipher real): los mismos tres casos que arriba con el navegador real,
combinados además con `status=ReviewStatus.UNVERIFIED` (`"exclude"` → solo B).

`tests/unit/evaluation/test_review_metrics_hidden.py`:
- `test_hidden_counts`: con C revisado como `CORRECTED`, D revisado como `REJECTED` y E (`UNVERIFIED`,
  `(PREDICTED_ILLEGIBLE,)`, sin revisar), `hidden_total == 3`, `hidden_legible == 1`, `hidden_unusable == 1`,
  `hidden_pending == 1`; sin ocultos, los cuatro son 0.

`tests/unit/cli/test_review_evaluation_hidden.py`:
- `test_summary_includes_hidden_line`: con `_write_summary` sobre un `ReviewMetrics` con `hidden_total=3`,
  `hidden_legible=1`, `hidden_unusable=1`, `hidden_pending=1` y el nombre de reporte `r.json`, la salida estándar tiene
  tres líneas y la segunda es exactamente `ocultas=3 ocultas_legibles=1 ocultas_inservibles=1 ocultas_pendientes=1`.

## Fuera de alcance
- Pestaña "Ocultas por baja calidad" en la web: la API la expone en la spec 066 y la pantalla en la 071.
- GUI PySide6: sin cambios.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde, sin modificar tests existentes.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -nE "execute\(f|execute\(.*%|execute\(.*\+" src/` sin resultados.
