# 048 - GUI: página "Lecturas" (galería de placas con revisión en panel lateral)

## Objetivo
Sustituir la tabla de avistamientos y el diálogo modal de revisión por una página que se entiende sola: una galería
de tarjetas (recorte + lectura + estado, spec 047) con filtros en forma de botones con contador, y un panel lateral que
muestra la placa elegida en grande y permite decidir con un clic o una tecla. Tras cada decisión se pasa sola a la
siguiente placa. Esta spec crea la página; la spec 049 la pone en la ventana principal.

## Depende de
041, 046, 047.

## Archivos rectores aplicables
- ADR-015; ARQUITECTURA.md §6 (tamaños), §7 (mientras procesa, la GUI no escribe).
- reglas-seguridad.md SEG-05, SEG-07 (recortes solo en memoria), SEG-26, SEG-27.

## Archivos a crear/modificar
- `src/lector_placas/gui/labels.py` (añadir `PROFILE_LABELS` y `profile_label`)
- `src/lector_placas/gui/review_panel.py` (nuevo: `ReviewPanel`)
- `src/lector_placas/gui/readings_filters.py` (nuevo: `ReadingsFilters`)
- `src/lector_placas/gui/readings_page.py` (nuevo: `ReadingsPage`)
- `tests/unit/gui/test_review_panel.py`, `tests/unit/gui/test_readings_filters.py`,
  `tests/unit/gui/test_readings_page.py` (nuevos); `tests/unit/gui/test_labels.py` (añadir casos)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# gui/labels.py (añadidos)
PROFILE_LABELS: Final[Mapping[str, tuple[str, str]]]   # clave de perfil -> (nombre, descripción)
def profile_label(profile: str) -> str: ...

# gui/review_panel.py
PANEL_WIDTH: Final[int] = 380
PANEL_CROP_BOX: Final[tuple[int, int]] = (340, 120)
class ReviewPanel(QFrame):
    decided = Signal(object)            # ReviewDecision (CONFIRM, CORRECT o REJECT)
    skip_requested = Signal()
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def show_record(self, record: SightingRecord, crop: ImageBGR | None, crop_note: str | None) -> None: ...
    def clear(self) -> None: ...
    def set_actions_enabled(self, enabled: bool) -> None: ...
    def is_editing(self) -> bool: ...
    def confirm(self) -> None: ...
    def start_edit(self) -> None: ...
    def reject(self) -> None: ...
    def skip(self) -> None: ...

# gui/readings_filters.py
FILTER_ORDER: Final[tuple[ReviewStatus | None, ...]] = (
    ReviewStatus.UNVERIFIED, ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED, ReviewStatus.REJECTED, None)
class ReadingsFilters(QWidget):
    changed = Signal()
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def status(self) -> ReviewStatus | None: ...
    def set_status(self, status: ReviewStatus | None) -> None: ...
    def set_counts(self, counts: Mapping[ReviewStatus | None, int]) -> None: ...
    def set_runs(self, runs: Sequence[RunRecord]) -> None: ...
    def run_id(self) -> int | None: ...
    def set_run_id(self, run_id: int | None) -> None: ...
    def plate_prefix(self) -> str | None: ...

# gui/readings_page.py
PAGE_SIZE: Final[int] = 60
class ReadingsPage(QWidget):
    pending_changed = Signal(int)
    def __init__(self, session: GuiSession) -> None: ...
    def reload(self) -> None: ...
    def show_run(self, run_id: int | None, status: ReviewStatus | None) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
    def pending_count(self) -> int: ...
```

## Comportamiento esperado
1. **`labels.py`**: `PROFILE_LABELS` = `parqueadero` → ("Parqueadero o entrada", "Vehículos lentos o detenidos, cerca
   de la cámara"); `calle_lenta` → ("Calle con tráfico lento", "Tráfico urbano normal"); `calle_rapida` → ("Vía rápida",
   "Vehículos a mayor velocidad"). `profile_label(p)` devuelve el nombre, o para un perfil desconocido
   `p.replace("_", " ").capitalize()`.
2. **`ReviewPanel`** (`QFrame`, ancho fijo `PANEL_WIDTH`, fondo `SURFACE`):
   - Sin registro (`clear`): solo un `EmptyState` (spec 047) con título "Elige una placa" y pista "Haz clic en una
     tarjeta para verla en grande y revisarla.".
   - Con registro (`show_record`): recorte con `bgr_to_pixmap(crop, *PANEL_CROP_BOX)` o, si `crop` es `None`, el texto
     `crop_note` (o "sin imagen"); la lectura vigente en un `QLabel` `objectName` `"PlateText"` con `format_plate`; la
     etiqueta de estado (`STATUS_BADGES`, `STATUS_COLORS`); si `ocr_text != plate_text`, una línea
     `f"El sistema leyó: {format_plate(ocr_text)}"`; "Seguridad del lector" con una barra `QProgressBar` 0–100 con el
     valor `round(confidence * 100)` y el texto `percent(confidence)`; si hay razones, el título "Por qué revisarla" y una
     línea `"• " + REASON_TEXTS[r]` por razón; y una línea `role="muted"`
     `f"{VEHICLE_LABELS[tipo].capitalize()} · aparece en {short_time(first_seen_ms)}–{short_time(last_seen_ms)} ·
     video {run_id}"`.
   - Acciones (visibles solo con registro): botón `role="primary"` "✓ Es correcta   C"; "✎ Corregir   E";
     "✗ No es una placa   R"; `role="ghost"` "Saltar   S". Sus clics llaman `confirm`, `start_edit`, `reject`, `skip`.
   - `confirm()` emite `decided(ReviewDecision(CONFIRM))`; `reject()` emite `REJECT`; `skip()` emite `skip_requested`.
     Los tres no hacen nada si no hay registro, si las acciones están deshabilitadas o si se está editando.
   - `start_edit()`: muestra un `QLineEdit` con el texto vigente seleccionado, máximo 10, validador
     `^[A-Za-z0-9]{0,10}$`, que pasa a mayúsculas lo escrito, con el foco; y los botones "Guardar   Enter"
     (`role="primary"`) y "Cancelar   Esc"; oculta las cuatro acciones. Enter o "Guardar": si el texto cumple
     `PLATE_TEXT_REGEX` y es distinto de `plate_text` → emite `ReviewDecision(CORRECT, texto)`; si es igual → emite
     `CONFIRM`; si no cumple → muestra en rojo "Escribe solo letras y números (1 a 10)" y sigue editando. Esc o
     "Cancelar" → vuelve a las acciones sin emitir. `is_editing()` informa el modo.
   - `set_actions_enabled(False)`: deshabilita las acciones y muestra la nota `role="muted"` "Espera a que termine el
     procesamiento para revisar."; `True` la oculta y las habilita.
   - Ningún texto de placa en títulos, tooltips ni portapapeles; el panel no registra nada en el log.
3. **`ReadingsFilters`** (una fila):
   - Botones conmutables exclusivos (`QButtonGroup`), uno por valor de `FILTER_ORDER`, con el texto
     `f"{nombre} ({n})"`: nombres "Por revisar", "Confirmadas", "Corregidas", "Descartadas", "Todas"; `n` viene de
     `set_counts` (0 si falta). `set_status` marca el botón sin emitir `changed`; el clic del operador emite `changed`.
   - Campo de búsqueda con texto de ayuda "Buscar placa…", máximo 10, validador `^[A-Za-z0-9]{0,10}$`;
     `plate_prefix()` devuelve el texto en mayúsculas o `None` si está vacío. Emite `changed` 300 ms después de la
     última tecla (`QTimer` de un disparo reiniciado en cada cambio).
   - `QComboBox` de videos: primera opción "Todos los videos" y una por corrida de `set_runs` con el texto
     `f"Video {run_id} · {started_at local %d/%m %H:%M} · {profile_label(profile)}"`. `set_runs` conserva la corrida
     elegida si sigue en la lista. `run_id()` devuelve el id elegido o `None`; `set_run_id` lo elige sin emitir; el cambio
     del operador emite `changed`.
4. **`ReadingsPage`**:
   - Diseño: arriba el título "Lecturas" (`role="title"`) y los `ReadingsFilters`; debajo un `QSplitter` horizontal con
     un `CardGrid` a la izquierda (con un botón "Mostrar más" debajo) y el `ReviewPanel` a la derecha.
   - `reload()`: `browser.list_runs(50, 0)` → `filters.set_runs`; cuenta por estado con `browser.count_sightings`
     (cuatro estados y "Todas", respetando el video y la búsqueda elegidos) → `filters.set_counts`; emite
     `pending_changed(n)` con los pendientes **globales** (sin filtros de video ni búsqueda); y carga la primera página
     con la consulta vigente (`SightingQuery(status, plate_prefix, run_id)`, `PAGE_SIZE`, offset 0). Se llama al
     crear la página; si hay pendientes, el filtro inicial es "Por revisar", si no "Todas".
   - Recortes de la galería: por cada registro de la página, `crop_store.load(crop_ref)` → `bgr_to_pixmap(img,
     *CROP_BOX)`; `crop_ref` `None`, `CropNotFoundError`, `CropStoreError` o `EncryptionError` → sin imagen. Los
     `QPixmap` viven solo en las tarjetas (SEG-07, SEG-27).
   - "Mostrar más": visible solo si quedan resultados; carga la página siguiente con `append_records`.
   - `filters.changed` → recuenta y recarga desde la primera página (sin selección; panel vacío).
   - Mensajes de galería vacía (`set_empty_message`): sin ningún avistamiento en la base → "Aún no hay lecturas" /
     "Procesa un video para ver aquí las placas encontradas."; filtro "Por revisar" sin resultados y sin búsqueda →
     "¡Todo revisado!" / "No quedan placas pendientes."; cualquier otro caso → "Sin resultados" / "Prueba con otra
     placa o quita los filtros.".
   - Selección de una tarjeta → carga su recorte de nuevo (`crop_store.load`; mismos errores; nota
     "La imagen ya se borró por antigüedad." para `CropNotFoundError` y "No se pudo abrir la imagen." para
     `CropStoreError`/`EncryptionError`) y `panel.show_record(record, crop, nota)`.
   - `panel.decided` → `DecideSighting(session.repository, session.clock).execute(id, decision)`. Con el registro
     actualizado: si su nuevo estado sigue entrando en el filtro de estado vigente, `grid.update_record`; si no,
     `grid.remove`. En ambos casos se selecciona `next_id` (calculado **antes** de quitarla) o, si no hay, se vacía el
     panel; se recuentan los filtros y se emite `pending_changed`. `ReviewError`, `SightingNotFoundError` o
     `RepositoryError` → `QMessageBox.warning(self, "lectorPlacas", str(error))` (constante del módulo; no importar `main_window`).
   - `panel.skip_requested` → selecciona `next_id` sin escribir nada.
   - Atajos (`QShortcut` con contexto `Qt.WidgetWithChildrenShortcut` sobre la página): C → `panel.confirm`,
     E → `panel.start_edit`, R → `panel.reject`, S → `panel.skip`. No actúan mientras `panel.is_editing()`.
   - `show_run(run_id, status)`: fija video y estado en los filtros (sin emitir) y recarga desde la primera página;
     luego selecciona la primera tarjeta si hay.
   - `set_busy(b)` → `panel.set_actions_enabled(not b)` (ARQUITECTURA §7: mientras procesa, la GUI no escribe).
   - `pending_count()` devuelve el último total global de pendientes.
   - Errores de lectura (`RepositoryError`) al recontar o cargar → se muestra la galería vacía con "No se pudieron
     cargar las lecturas" / el mensaje del error; no se abre diálogo.

## Casos borde y manejo de errores
- Decidir la última tarjeta de la lista: el panel queda vacío y la galería muestra su mensaje vacío si corresponde.
- Búsqueda en minúsculas: se consulta en mayúsculas.
- La placa solo aparece dentro de tarjetas y panel; nunca en títulos, logs, tooltips ni mensajes de error.

## Tests de aceptación
Sin pantalla (conftest de la spec 042). `GuiSession` armada con `InMemoryPlateRepository` (también navegador),
`InMemoryCropStore`, `InMemoryExportStore` y `FakeClock` de `tests/fixtures/fakes.py`, sembrada con avistamientos
sintéticos (`ABC123`, `XYZ98K`, …) en varios estados, dos corridas y recortes numpy. `QMessageBox` se sustituye con
`monkeypatch`. Las teclas se envían con `QTest.keyClick`/`keyClicks`.

1. `test_labels.py` (añadir): `test_profile_label_known_and_unknown`.
2. `test_review_panel.py`:
   - `test_empty_panel_shows_hint`.
   - `test_show_record_displays_plate_badge_reasons_and_ocr_line`: con `ocr_text` distinto aparece "El sistema leyó";
     con igual no aparece; una línea por razón con el texto de `REASON_TEXTS`.
   - `test_confirm_and_reject_emit_decisions`.
   - `test_edit_correct_emits_corrected_text`: `start_edit`, escribir `xyz98k`, Enter → `CORRECT` con `"XYZ98K"`.
   - `test_edit_same_text_confirms` y `test_edit_invalid_text_shows_message` (texto vacío + Enter → mensaje, sigue
     editando, nada emitido); Esc cancela sin emitir.
   - `test_disabled_actions_do_not_emit_and_show_note`.
3. `test_readings_filters.py`:
   - `test_counts_render_in_buttons`.
   - `test_set_status_does_not_emit_but_click_does`.
   - `test_search_is_debounced_and_uppercased` (esperar con `QTest.qWait(400)`; varias teclas → un solo `changed`).
   - `test_runs_combo_lists_runs_and_keeps_selection`.
4. `test_readings_page.py`:
   - `test_initial_filter_is_pending_when_there_are_pending`, y `"Todas"` cuando no hay.
   - `test_cards_have_crops_or_placeholder`.
   - `test_filter_change_reloads_first_page_and_counts`.
   - `test_show_more_appends_next_page` (con 130 avistamientos: 60 + 60 + 10).
   - `test_decision_removes_card_from_pending_and_selects_next`: en "Por revisar", confirmar la tarjeta elegida la
     quita, selecciona la siguiente, baja el contador y emite `pending_changed`.
   - `test_decision_in_all_filter_updates_card_in_place`.
   - `test_shortcuts_confirm_and_skip` (C y S con la página visible; E abre la edición y C ya no confirma).
   - `test_busy_blocks_decisions`.
   - `test_empty_messages` (base vacía; "Por revisar" sin pendientes).
   - `test_show_run_sets_filters_and_selects_first`.
   - `test_decision_error_shows_warning` (el repositorio lanza `RepositoryError` en `record_review`).

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- `wc -l src/lector_placas/gui/*.py`: ningún módulo pasa de 300 líneas; ninguna clase de 150.
