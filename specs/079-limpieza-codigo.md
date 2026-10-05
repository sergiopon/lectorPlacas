# 079 - Limpieza de código sin uso

## Objetivo
Quitar del repositorio el código, las dependencias y los artefactos que nadie usa, y dejar declaradas las dependencias
que sí se importan. No cambia el comportamiento de `lector` ni de `lector-web`.

## Depende de
073, 078.

## Archivos rectores aplicables
- ARQUITECTURA.md §6 (convenciones), docs/02-contratos.md (lo actualiza el orquestador, no el implementador).
- reglas-seguridad.md §8 (checklist).

## Archivos a crear/modificar
- `tests/architecture/test_gui_rules.py` (borrar)
- `src/lector_placas/infrastructure/model_registry.py`
- `src/lector_placas/web/demo.py`
- `src/lector_placas/web/schemas.py`
- `src/lector_placas/domain/plate_formats.py`
- `src/lector_placas/application/track_registry.py`
- `tests/unit/domain/test_plate_formats.py`
- `tests/unit/application/test_track_registry.py`
- `tests/integration/test_low_quality_filter.py`
- `tests/integration/test_schema_v3.py`
- `tests/integration/test_nivel_f_web.py`
- `tests/integration/test_gpu_environment.py`
- `frontend/src/api/index.ts`
- `frontend/e2e/capturas.spec.ts`
- `docs/img/web-historial.png` (borrar)
- `pyproject.toml`
- `uv.lock`
- `.pre-commit-config.yaml`

## Dependencias externas
Ninguna nueva. `starlette==1.7.0` ya está instalado (llega con `fastapi==0.141.1`; versión tomada de `uv.lock`).

## Interfaces y tipos involucrados
Se eliminan, sin sustituto:
- `MANIFEST_VERSION` (constante, `infrastructure/model_registry.py`).
- `PLATE_SIZE` (constante, `web/demo.py`).
- `class ErrorOut` (`web/schemas.py`).
- `def text_pattern(text: str) -> str` (`domain/plate_formats.py`).
- `TrackRegistry.active_count` (propiedad, `application/track_registry.py`).
- `export async function getSighting(id: number)` (`frontend/src/api/index.ts`).

Se conservan expresamente (no tocar): `ConfusionMap.default()` y `network_guard.is_network_blocked()`.

## Comportamiento esperado
1. Borrar el archivo `tests/architecture/test_gui_rules.py` entero.
2. Borrar cada símbolo de la lista anterior: la definición completa, su docstring y las líneas en blanco sobrantes que
   deje. Si tras borrarlo un import del mismo archivo queda sin uso (lo detecta `uv run ruff check .` como F401), borrar también ese import.
3. `tests/unit/domain/test_plate_formats.py`: borrar `test_text_pattern` y `test_text_pattern_rejects_invalid` con sus
   decoradores `@pytest.mark.parametrize`, y quitar `text_pattern` del import. Si `InvalidPlateTextError` queda sin uso,
   quitarlo del import.
4. `tests/unit/application/test_track_registry.py`, en `test_lifecycle_and_ordering`: borrar solo las dos líneas
   `assert registry.active_count == 2` y `assert registry.active_count == 0`. El resto del test no cambia.
5. En los cuatro archivos de `tests/integration/` de la lista, añadir tras los imports la línea
   `pytestmark = pytest.mark.integration` (y `import pytest` si no está). Ninguno de los cuatro define hoy
   `pytestmark`; los marcadores que ya tengan sus funciones (`@pytest.mark.gpu`) no se tocan.
6. `frontend/e2e/capturas.spec.ts`: borrar solo la línea
   `await page.screenshot({ path: '../docs/img/web-historial.png', animations: 'disabled' })`. Se conservan el clic en
   «Historial» y su `expect`. Borrar el archivo `docs/img/web-historial.png` con `git rm`.
7. `pyproject.toml`:
   - En `[project] dependencies`, borrar la línea `"scipy==1.18.1",` y añadir `"starlette==1.7.0",` justo después de
     la línea de `fastapi`.
   - En `[[tool.mypy.overrides]]`, quitar `"scipy.*", ` de la lista `module`.
   - En `[tool.ruff.lint.per-file-ignores]`, la entrada `"scripts/**"` pasa a `["S603", "S607"]`.
8. Ejecutar `uv lock`. En `uv.lock` solo puede cambiar la sección del paquete `lector-placas` (sus `dependencies` y
   `requires-dist`); `scipy` sigue en el lock como dependencia de `trackers`/`supervision` con la misma versión. Si el
   diff de `uv.lock` toca cualquier otro paquete, no lo aceptes: repórtalo.
9. `.pre-commit-config.yaml`: añadir al final de `hooks`, con la misma forma que los existentes (`language: system`,
   `pass_filenames: false`), dos hooks:
   - `id: frontend-typecheck`, `name: frontend typecheck`, `entry: npm --prefix frontend run typecheck`.
   - `id: frontend-test`, `name: frontend vitest`, `entry: npm --prefix frontend run test`.

## Casos borde y manejo de errores
- Si algún símbolo de la lista resulta usado en `src/`, `frontend/src/`, `frontend/e2e/`, `scripts/` o `training/`
  (comprobar con `grep -rn` antes de borrar), no lo borres y repórtalo.

## Tests de aceptación (en prosa)
No hay tests nuevos. La aceptación es:
- `grep -rn "MANIFEST_VERSION\|PLATE_SIZE\|ErrorOut\|text_pattern\|active_count" src tests` no devuelve nada.
- `grep -rn "getSighting(" frontend/src frontend/tests frontend/e2e` no devuelve nada (sí siguen `getSightingFrame` y
  los demás).
- `uv run pytest -q` ya no muestra `test_gui_rules.py` como omitido.
- `uv run pytest -q -m integration --collect-only` incluye los cuatro archivos de integración de la lista.

## Fuera de alcance
- Cambiar la lógica de cualquier módulo. Tocar `training/`, `scripts/`, `config/` o la documentación.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `cd frontend && npm run typecheck && npm run test` en verde.
- [ ] `git diff main -- uv.lock` solo toca la sección `lector-placas`.
