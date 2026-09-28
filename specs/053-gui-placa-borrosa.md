# 053 - GUI: botón y filtro "Placa borrosa"

## Objetivo
Llevar a la galería de revisión la decisión `ILLEGIBLE` de la spec 052: un botón "Placa borrosa" con atajo `B` en el
panel lateral, un filtro "Borrosas" en la fila de filtros y las dos métricas nuevas en la pestaña de mantenimiento.
El operador distingue así "no es una placa" (Descartada) de "es una placa, pero no se lee" (Borrosa).

## Depende de
046, 047, 048, 052.

## Archivos rectores aplicables
- ADR-015 y ARQUITECTURA.md: la GUI solo importa `lector_placas.cli.composition` de la CLI; límites de §6 (clases
  ≤ 150 líneas, módulos ≤ 300).
- reglas-seguridad.md SEG-27 (GUI), SEG-05 (sin texto de placa en logs).

## Archivos a crear/modificar
- `src/lector_placas/gui/review_panel.py`
- `src/lector_placas/gui/review_actions.py` (nuevo; ver punto 1)
- `src/lector_placas/gui/readings_page.py`
- `src/lector_placas/gui/readings_filters.py`
- `src/lector_placas/gui/maintenance_tab.py`
- `tests/unit/gui/test_review_panel.py`
- `tests/unit/gui/test_readings_page.py`
- `tests/unit/gui/test_readings_filters.py`
- `tests/unit/gui/test_maintenance_tab.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
- `ReviewPanel.mark_illegible() -> None`: nuevo, análogo a `reject()`. Emite
  `decided(ReviewDecision(ReviewAction.ILLEGIBLE))` si `_can_decide()`.
- Sin cambios en señales, en `DecideSighting` ni en `GuiSession`: la decisión viaja por el mismo camino que
  `REJECT`. `DecideSighting` ya la acepta desde la 052.

## Comportamiento esperado
1. **Tamaño de módulo:** `review_panel.py` tiene hoy 300 líneas, el máximo. El constructor de la columna de acciones
   (`_make_actions` y `_make_button`, con los textos de los botones) se mueve a `gui/review_actions.py`, que
   `review_panel.py` importa. Sin cambio de comportamiento, salvo el botón nuevo. Ambos módulos quedan ≤ 300 líneas.
2. **Botones del panel**, en este orden:
   - `"✓ Es correcta   C"` (primary)
   - `"✎ Corregir   E"`
   - `"✗ No es una placa   R"`
   - `"◐ Placa borrosa   B"` (nuevo), conectado a `mark_illegible`
   - `"Saltar   S"` (ghost)

   El botón nuevo forma parte de `panel._buttons`, así que se habilita y deshabilita con los demás
   (`set_actions_enabled`).
3. **Atajo:** en `readings_page._build_shortcuts`, `("B", panel.mark_illegible)`, con el mismo contexto que los demás.
   En modo edición no dispara nada (lo garantiza `_can_decide`).
4. **Filtro:** `FILTER_ORDER` queda `UNVERIFIED, CONFIRMED, CORRECTED, REJECTED, ILLEGIBLE, None`, y
   `FILTER_LABELS[ILLEGIBLE] = "Borrosas"`. Los conteos por filtro se calculan igual que los demás.
5. **Tarjetas y panel:** el badge y los colores de `ILLEGIBLE` salen de los mapas que ya añadió la 052 (`"Borrosa"`,
   gris). No hace falta ningún cambio en las tarjetas.
6. **Mantenimiento:** en `_METRIC_ROWS`, `("Confirmadas borrosas", "confirmed_illegible", False)` va justo después
   de "Confirmadas rechazadas", y `("Sin verificar borrosas", "unverified_illegible", False)` justo después de
   "Sin verificar rechazadas". El combo de exportación ya recorre `ReviewStatus`, así que incluye "borrosa" sin cambios.
7. Tras decidir `ILLEGIBLE` en el filtro "Por revisar", la tarjeta sale de la lista y se selecciona la siguiente, igual
   que con `REJECT`.

## Casos borde y manejo de errores
- Acciones deshabilitadas (procesamiento en curso): `B` y el botón no emiten nada.
- Sin registro elegido: `mark_illegible` no emite nada.

## Tests de aceptación
Con los fixtures existentes (`qapp`, `config`, `show_page`, sesión con repositorio en memoria o de prueba, como en los
tests actuales de cada archivo) y `QT_QPA_PLATFORM=offscreen`.

### `tests/unit/gui/test_review_panel.py`
1. `test_mark_illegible_emits_decision`: con un registro mostrado, `mark_illegible()` y el clic en el botón
   `"◐ Placa borrosa   B"` emiten `ReviewDecision(ReviewAction.ILLEGIBLE)`. Sin registro no emite nada.
2. `test_actions_order_includes_illegible`: los textos de `panel._buttons` son, en orden, los cinco del punto 2.
3. Los casos existentes de acciones deshabilitadas y rehabilitadas cubren también el botón nuevo, porque recorren
   `panel._buttons`; pasan sin cambios.

### `tests/unit/gui/test_readings_page.py`
4. `test_shortcut_b_marks_illegible_and_advances`: en el filtro "Por revisar", con dos pendientes, pulsar `B` deja el
   primero `ILLEGIBLE` en el repositorio, lo quita de la galería y selecciona el siguiente. El conteo de "Por revisar"
   baja en uno.

### `tests/unit/gui/test_readings_filters.py`
5. `test_illegible_filter_button`: existe el botón de `ILLEGIBLE` con el texto `"Borrosas"` (y `"Borrosas (n)"` tras
   `set_counts`), situado entre "Descartadas" y "Todas".

### `tests/unit/gui/test_maintenance_tab.py`
6. `_METRIC_FIELDS` añade `confirmed_illegible` y `unverified_illegible` en las posiciones del punto 6, y el test de
   métricas existente comprueba que se muestran. Si el dataset de prueba no tiene borrosas, los valores son 0.

## Fuera de alcance
- Cambios en la CLI, la persistencia o las métricas (spec 052).
- Atajos configurables.

## Definition of Done
- `QT_QPA_PLATFORM=offscreen uv run pytest tests/unit/gui tests/architecture` pasa.
- `uv run pytest` completo pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores; `wc -l` de
  `review_panel.py` y `review_actions.py` ≤ 300.
- Solo cambian los archivos listados.
