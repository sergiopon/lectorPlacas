# 044 - GUI: pestaña "Avistamientos" (búsqueda, detalle con recorte) y revisión en diálogo Qt

## Objetivo
Listar y filtrar avistamientos con paginación, ver el recorte descifrado en memoria y revisar (confirmar, corregir,
rechazar) con un diálogo Qt que implementa el puerto `ReviewUI`, reutilizando `ReviewSightings` sin cambios.

## Depende de
038, 041, 042, 043.

## Archivos rectores aplicables
- ADR-015; ARQUITECTURA.md §4 (`QtReviewUI`), §7 (revisión con diálogo modal).
- reglas-seguridad.md SEG-05, SEG-07 (recortes solo en memoria), SEG-26, SEG-27 (sin portapapeles, sin estado
  persistido, títulos constantes).
- Spec 034 (mismas acciones y teclas que la revisión en la ventana OpenCV).

## Archivos a crear/modificar
- `src/lector_placas/gui/widgets.py` (nuevo: `NoCopyTableView`)
- `src/lector_placas/gui/labels.py` (nuevo: textos en español de estados, tipos y formatos de tiempo)
- `src/lector_placas/gui/review_dialog.py` (nuevo: `ReviewDialog` y `QtReviewUI`)
- `src/lector_placas/gui/sightings_tab.py` (nuevo: filtros, modelo de tabla, detalle y acciones de revisión)
- `src/lector_placas/gui/main_window.py` (inserta la pestaña y conecta `busy_changed` y `run_finished`)
- `src/lector_placas/gui/process_tab.py` (usa `labels.py` y `NoCopyTableView` para la tabla de corridas)
- `src/lector_placas/gui/runs_model.py` (nuevo: `RunsTableModel` y `RUN_COLUMNS` salen de `process_tab.py`)
- `src/lector_placas/gui/sightings_model.py` (nuevo: `SightingsTableModel`, `SIGHTING_COLUMNS` y textos de detalle)
- `src/lector_placas/gui/sightings_filters.py` (nuevo: widget de filtros de la pestaña Avistamientos)
- `src/lector_placas/gui/sightings_detail.py` (nuevo: widget de detalle con el recorte)
- `tests/unit/gui/test_labels.py`, `tests/unit/gui/test_widgets.py`, `tests/unit/gui/test_review_dialog.py`,
  `tests/unit/gui/test_sightings_tab.py` (nuevos); `tests/unit/gui/test_process_tab.py` (solo imports, si cambian)

Tamaño (ARQUITECTURA §6): cada módulo ≤ 300 líneas y cada clase ≤ 150. Los nombres públicos del contrato siguen
importables desde el módulo que indica el contrato (`process_tab.RunsTableModel`, `sightings_tab.SightingsTableModel`,
`sightings_tab.SIGHTING_COLUMNS`, …), reexportándolos si se movieron. `ReviewDialog` puede delegar la lógica del texto
en edición en una clase auxiliar privada del mismo módulo.

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# gui/labels.py
STATUS_LABELS: Final[Mapping[ReviewStatus, str]]      # confirmed "confirmado", unverified "sin verificar",
                                                     # corrected "corregido", rejected "rechazado"
VEHICLE_LABELS: Final[Mapping[VehicleType, str]]      # car "carro", motorcycle "moto", bus "bus", truck "camión"
RUN_STATUS_LABELS: Final[Mapping[RunStatus, str]]     # completed "completada", failed "fallida", running "en curso"
def video_time(ms: int) -> str: ...                   # "mm:ss.mmm"; horas si >= 1 h: "h:mm:ss.mmm"
def local_datetime(value: datetime) -> str: ...       # hora local "%Y-%m-%d %H:%M:%S"
def percent(value: float) -> str: ...                 # 0.873 -> "87 %"

# gui/widgets.py
class NoCopyTableView(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def keyPressEvent(self, event: QKeyEvent) -> None: ...

# gui/review_dialog.py
REVIEW_TITLE: Final[str] = "Revisión"
INVALID_TEXT: Final[str] = "texto inválido"
class ReviewDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def present(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...   # llama exec()
class QtReviewUI:                                     # implementa ReviewUI
    def __init__(self, parent: QWidget | None) -> None: ...
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...

# gui/sightings_tab.py
PAGE_SIZE: Final[int] = 100
SIGHTING_COLUMNS: Final[tuple[str, ...]] = ("ID", "Fecha", "Corrida", "Tipo", "Placa", "OCR", "Estado",
                                            "Confianza", "Lecturas", "Razones")
class SightingsTableModel(QAbstractTableModel):
    def set_records(self, records: Sequence[SightingRecord]) -> None: ...
    def record_at(self, row: int) -> SightingRecord: ...
class SightingsTab(QWidget):
    def __init__(self, session: GuiSession) -> None: ...
    def current_query(self) -> SightingQuery: ...
    def search(self) -> None: ...                      # vuelve a la página 1
    def set_busy(self, busy: bool) -> None: ...
    def review(self, status: ReviewStatus) -> None: ...
```

## Comportamiento esperado
1. **`labels.py`**: funciones puras según el contrato. `video_time(0)` → `"00:00.000"`; `video_time(83_456)` →
   `"01:23.456"`; `video_time(3_723_004)` → `"1:02:03.004"`. `local_datetime` convierte con `astimezone()` (sin argumento).
2. **`NoCopyTableView`** (SEG-27): sin menú contextual (`Qt.NoContextMenu`), sin edición (`NoEditTriggers`),
   selección de una fila completa. `keyPressEvent` ignora el evento si coincide con `QKeySequence.StandardKey.Copy`
   (no llama a la implementación base, que copiaría la celda al portapapeles); cualquier otra tecla pasa a la base.
3. **`ReviewDialog.present(record, crop)`** (modal, título `REVIEW_TITLE`):
   - Muestra el recorte con `bgr_to_qimage` escalado para caber en 640×220 conservando proporción (o el texto
     "sin recorte" si `crop` es `None`); datos: `#sighting_id`, corrida, tipo (`VEHICLE_LABELS`), estado
     (`STATUS_LABELS`), "Texto OCR", "Texto actual" (`plate_text`), confianza, acuerdo, lecturas y razones
     (`", ".join(r.value …)` o "-"). Un `QLineEdit` con `plate_text`, de solo lectura mientras no se edita.
   - Botones y teclas (mismas letras que la spec 034): "Confirmar [C]", "Editar [E]", "Rechazar [R]", "Saltar [S]",
     "Salir [Esc]". En **modo menú**: C → `CONFIRM`; R → `REJECT`; S → `SKIP`; Esc o cerrar la ventana → `QUIT`;
     E → **modo edición**. En **modo edición**, las letras escriben en el campo (se convierten a mayúsculas, máximo 10,
     solo `A-Z0-9`): Enter → si el texto cumple `PLATE_TEXT_REGEX` y es distinto de `plate_text` →
     `ReviewDecision(CORRECT, texto)`; si es igual → `CONFIRM`; si no cumple → muestra `INVALID_TEXT` y sigue en edición.
     Esc en edición → vuelve al modo menú restaurando `plate_text`.
   - En modo menú, cualquier otra tecla (incluidas Enter y Espacio) no hace nada: los botones no reciben foco
     (`Qt.NoFocus`) ni son botón por defecto (`autoDefault`/`default` en `False`), para que Enter no confirme por
     accidente. El campo de texto lleva delante la etiqueta "Texto actual".
   - Devuelve la decisión al cerrarse el `exec()`. No escribe nada a disco ni al portapapeles; no registra el texto.
4. **`QtReviewUI`**: crea un único `ReviewDialog(parent)` perezosamente y lo reutiliza en cada `ask`; `close()` lo
   cierra y descarta (idempotente). Así `ReviewSightings.execute` funciona sin cambios: su bucle llama `ask` y el
   `exec()` del diálogo mantiene vivo el bucle de eventos.
5. **`SightingsTableModel`**: columnas `SIGHTING_COLUMNS`: `sighting_id`, `local_datetime(created_at)`, `run_id`,
   `VEHICLE_LABELS`, `plate_text`, `ocr_text`, `STATUS_LABELS`, `percent(confidence)`, `num_readings`, razones
   (`", ".join(r.value …)` o "-"). Solo lectura; alineación a la derecha de los números.
6. **`SightingsTab`** (pestaña "Avistamientos"):
   - Filtros: estado (`QComboBox` con "Todos" + los cuatro de `STATUS_LABELS`); placa (`QLineEdit`, máximo 10,
     validador `^[A-Za-z0-9]{0,10}$`, se pasa a mayúsculas; vacío = sin filtro); corrida (`QSpinBox` 0–2 147 483 647,
     0 muestra "todas"); desde y hasta (`QCheckBox` + `QDateEdit` cada uno, desactivados por defecto). Botones
     "Buscar" y "Limpiar".
   - `current_query()`: construye `SightingQuery`; "desde" = medianoche local del día elegido; "hasta" = medianoche
     local del **día siguiente** al elegido (el día elegido queda incluido); ambas como `datetime` con zona local
     (`datetime(..).astimezone()`). Si `SightingQuery` lanza `InvalidEntityError` (rango invertido), `search` muestra
     `QMessageBox.warning` con `"rango de fechas inválido"` y no consulta.
   - `search()` y paginación: `browser.count_sightings(query)` y `browser.search_sightings(query, PAGE_SIZE, offset)`;
     etiqueta `f"página {n} de {total_paginas} ({total} avistamientos)"` (con 0 resultados: "sin resultados");
     botones "Anterior"/"Siguiente" habilitados según corresponda. `RepositoryError` → `QMessageBox.warning` con el
     mensaje. La tabla es un `NoCopyTableView`. Se ejecuta una búsqueda sin filtros al crear la pestaña.
   - Detalle al seleccionar una fila: recorte con `session.crop_store.load(crop_ref)` → `bgr_to_qimage` escalado a
     480×160 como máximo; `crop_ref` `None` → "sin recorte"; `CropNotFoundError` → "recorte no disponible (purgado)";
     otro `CropStoreError` o `EncryptionError` → "no se pudo leer el recorte". Datos: aparición
     `video_time(first_seen_ms)`–`video_time(last_seen_ms)`, `reviewed_at` (local) o "sin revisar", formatos
     (`", ".join(format_ids)` o "-"). Al cambiar la selección o la página se descarta el recorte anterior.
   - Revisión: `QSpinBox` límite 1–10000 (50 por defecto) y botones "Revisar sin verificar" y "Auditar confirmadas".
     `review(status)`: `ReviewSightings(session.repository, session.crop_store, QtReviewUI(self), session.clock)
     .execute(limite, status)`; al terminar, `QMessageBox.information` con
     `f"confirmados={…} corregidos={…} rechazados={…} omitidos={…}"` y `search()`. `ReviewError`, `RepositoryError`,
     `CropStoreError` o `EncryptionError` → `QMessageBox.warning` con el mensaje.
   - `set_busy(True)` deshabilita los dos botones de revisión (mientras procesa solo se lee); `set_busy(False)` los
     habilita.
7. **`MainWindow`**: reemplaza la pestaña "Avistamientos" por `SightingsTab(session)`; conecta `busy_changed` a
   `SightingsTab.set_busy` y `ProcessTab.run_finished` a `SightingsTab.search`.
8. **`ProcessTab`** (spec 043): la tabla de corridas pasa a ser `NoCopyTableView` y usa `RUN_STATUS_LABELS` y
   `local_datetime` de `labels.py` en lugar de sus textos propios (mismos textos).

## Casos borde y manejo de errores
- Placa buscada en minúsculas: se convierte a mayúsculas antes de consultar.
- Un avistamiento revisado desaparece de "sin verificar" en la siguiente búsqueda.
- El texto de placa se ve solo en la tabla, el detalle y el diálogo; nunca en títulos, logs ni mensajes de error.

## Tests de aceptación
Sin pantalla (conftest de la spec 042). Datos sintéticos: `InMemoryPlateRepository` e `InMemoryCropStore` de
`tests/fixtures/fakes.py` sembrados con avistamientos de placas inventadas (`ABC123`, `XYZ98K`, …) y recortes numpy.
`QMessageBox` se sustituye con `monkeypatch`. El diálogo se prueba sin `exec()` bloqueante: los tests usan
`QTimer.singleShot(0, …)` para enviar teclas con `QTest.keyClick`/`keyClicks` al diálogo abierto, o sustituyen
`ReviewDialog.exec` por una función que simula las teclas y devuelve.

1. `test_labels.py`: `video_time` (los tres ejemplos del punto 1), `percent(0.873) == "87 %"`, etiquetas completas para
   todos los valores de `ReviewStatus`, `VehicleType` y `RunStatus`.
2. `test_widgets.py`: `test_copy_shortcut_does_not_touch_clipboard`: con la tabla enfocada y una fila seleccionada,
   `QTest.keySequence(view, QKeySequence.StandardKey.Copy)` no cambia el texto de `QGuiApplication.clipboard()` (el
   test fija antes un texto centinela y comprueba que sigue igual); sin menú contextual; sin edición.
3. `test_review_dialog.py`:
   - `test_confirm_reject_skip_quit_keys`: C, R, S y Esc devuelven la acción correspondiente.
   - `test_edit_and_correct`: E, escribir `xyz98k`, Enter → `CORRECT` con `"XYZ98K"`.
   - `test_edit_same_text_confirms`.
   - `test_enter_and_space_in_menu_do_nothing`: en modo menú, Enter y Espacio no cierran el diálogo; luego C →
     `CONFIRM`.
   - `test_edit_invalid_text_stays`: E, borrar todo, Enter → sigue abierto con `INVALID_TEXT` visible; luego Esc, Esc →
     `QUIT`.
   - `test_dialog_without_crop_shows_placeholder`.
   - `test_qt_review_ui_works_with_review_sightings`: `ReviewSightings` con `QtReviewUI` y dos avistamientos
     `unverified`, con respuestas simuladas C y luego R → `ReviewSummary(confirmed=1, rejected=1, …)` y el repositorio
     falso refleja ambos estados.
4. `test_sightings_tab.py`:
   - `test_initial_search_lists_all_descending` y la etiqueta de página.
   - `test_filters_build_query`: estado, placa en minúsculas → mayúsculas, corrida, fechas (hasta = día siguiente).
   - `test_inverted_date_range_warns`.
   - `test_pagination_next_previous` con 250 avistamientos (3 páginas).
   - `test_detail_shows_crop_and_handles_missing`: con recorte → pixmap no nulo; `crop_ref` inexistente → texto de
     purgado; `None` → "sin recorte".
   - `test_review_button_runs_review_and_refreshes` (con `ReviewDialog.exec` sustituido).
   - `test_busy_disables_review_buttons`.
   - `test_model_formats_columns`: una fila de ejemplo produce exactamente los textos esperados de cada columna.

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- Prueba manual (la hace el operador): buscar, ver recortes y revisar desde la GUI con datos propios.
