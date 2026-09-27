# 049 - GUI: ventana principal rediseñada y flujo guiado para procesar un video

## Objetivo
Cerrar el rediseño de la GUI: una ventana con dos lugares claros, **Procesar** y **Lecturas**, que guía al operador sin
instrucciones. Procesar es un flujo en tres pasos (elegir o arrastrar el video y el tipo de escena → ver el progreso con
las placas apareciendo en vivo → resumen con un botón para revisar lo pendiente). Las herramientas poco frecuentes
(exportar, retención, métricas, historial de videos) pasan a un menú "Más". Se eliminan la tabla de avistamientos, la
pestaña de procesar antigua y el diálogo modal de revisión (specs 043–044), que la galería de la spec 048 reemplaza.

## Depende de
043, 045, 047, 048.

## Archivos rectores aplicables
- ADR-015; ARQUITECTURA.md §6 (tamaños), §7 (hilos y conexiones; mientras procesa, la GUI no escribe).
- reglas-seguridad.md SEG-06 (la ruta del video no va a la BD), SEG-12 (validación del video), SEG-26, SEG-27.

## Archivos a crear/modificar
- `src/lector_placas/gui/process_page.py` (nuevo: `ProcessPage`, estados y conexión con el worker)
- `src/lector_placas/gui/process_views.py` (nuevo: vistas de inicio, en curso y resumen)
- `src/lector_placas/gui/tools_dialogs.py` (nuevo: `ToolsDialog` con la pestaña de mantenimiento y `RunsDialog`)
- `src/lector_placas/gui/main_window.py` (reescritura)
- Se **eliminan**: `src/lector_placas/gui/process_tab.py`, `sightings_tab.py`, `sightings_filters.py`,
  `sightings_detail.py`, `sightings_model.py`, `review_dialog.py` y sus tests `tests/unit/gui/test_process_tab.py`,
  `test_sightings_tab.py`, `test_review_dialog.py`.
- `tests/unit/gui/test_process_page.py`, `tests/unit/gui/test_tools_dialogs.py` (nuevos);
  `tests/unit/gui/test_main_window.py` (reescritura)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# gui/process_page.py
LIVE_REFRESH_S: Final[float] = 1.0
class ProcessPage(QWidget):
    busy_changed = Signal(bool)
    review_requested = Signal(object)       # run_id: int | None
    run_finished = Signal()
    def __init__(self, session: GuiSession) -> None: ...
    def choose_video(self, path: Path) -> None: ...     # valida y pasa al paso "listo para empezar"
    def start(self) -> None: ...
    def cancel(self) -> None: ...
    def is_busy(self) -> bool: ...
    def wait_for_worker(self) -> None: ...

# gui/process_views.py
def eta_text(elapsed_s: float, fraction: float | None) -> str | None: ...
class IdleView(QWidget): ...                # elegir/arrastrar video y tipo de escena
class RunningView(QWidget): ...             # progreso, cancelar y galería en vivo
class DoneView(QWidget): ...                # resumen y siguientes pasos

# gui/tools_dialogs.py
TOOLS_TITLE: Final[str] = "Exportar, retención y métricas"
RUNS_TITLE: Final[str] = "Historial de videos"
class ToolsDialog(QDialog):
    def __init__(self, session: GuiSession, parent: QWidget | None) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
class RunsDialog(QDialog):
    def __init__(self, session: GuiSession, parent: QWidget | None) -> None: ...

# gui/main_window.py
WINDOW_TITLE: Final[str] = "lectorPlacas"
class MainWindow(QMainWindow):
    busy_changed = Signal(bool)
    def __init__(self, session: GuiSession, purge: PurgeResult) -> None: ...
    def show_page(self, name: str) -> None: ...          # "procesar" | "lecturas"
    def current_page(self) -> str: ...
    def set_busy(self, busy: bool) -> None: ...
    def closeEvent(self, event: QCloseEvent) -> None: ...
```

## Comportamiento esperado
1. **`IdleView`** (centrada, ancho máximo 560 px, sobre una tarjeta `SURFACE` con esquinas redondeadas):
   - Título "Procesar un video" (`role="title"`), pista `role="muted"` "Arrastra un video aquí o elígelo desde tu
     equipo." y botón `role="primary"` "Elegir video…" que abre `QFileDialog.getOpenFileName` en
     `config.under_root(config.input.allowed_dirs[0])` con el filtro de extensiones permitidas (como la spec 043).
   - Acepta arrastrar y soltar (`setAcceptDrops(True)`): acepta el arrastre solo si trae exactamente una URL local
     con una extensión de `config.input.allowed_extensions`; al soltar llama `ProcessPage.choose_video(ruta)`.
   - Con un video elegido muestra su **nombre** (nunca la ruta completa), "¿Dónde se grabó?" y un `QRadioButton` por
     perfil de `config.profiles` con el texto `profile_label(p)` y debajo su descripción de `PROFILE_LABELS`
     (`role="muted"`; los perfiles desconocidos no tienen descripción); marcado el de `config.profile(None)`. Botón
     `role="primary"` "Empezar" y botón `role="ghost"` "Cambiar video".
   - Si la validación falla, el mensaje `str(error)` aparece en rojo debajo del botón (no es un diálogo) y no hay video
     elegido.
2. **`RunningView`**: título `f"Procesando {nombre}"`, `QProgressBar` (0–1000 o indeterminada si `fraction` es `None`,
   como la spec 043), una línea con `f"{n} placas encontradas"` y, si `eta_text` no es `None`, `" · " + eta`; botón
   `role="ghost"` "Cancelar" (tras pulsarlo: deshabilitado con el texto "Cancelando…"); debajo un `CardGrid` (spec
   047) con mensaje vacío "Buscando placas…" / "Las placas aparecerán aquí a medida que se encuentren.".
   `eta_text(elapsed, fraction)`: `None` si `fraction` es `None` o menor que 0,02; si no,
   `f"quedan ~{short_time(round(elapsed * (1 - fraction) / fraction * 1000))}"`.
3. **`DoneView`**:
   - Éxito: título `f"Listo: {n} placas encontradas"` con `n = confirmadas + sin verificar`; línea
     `f"{c} confirmadas automáticamente · {u} por revisar · {s} vehículos sin placa legible"`; botón `role="primary"`
     `f"Revisar {u} placas pendientes"` si `u > 0`, si no "Ver lecturas"; botón `role="ghost"` "Procesar otro video";
     y el `CardGrid` de la corrida (reutiliza el de la vista en curso o lo recarga).
   - Cancelado: título "Procesamiento cancelado" y la línea "Las placas encontradas hasta ahora se guardaron."; mismos
     dos botones ("Ver lecturas" si no hay pendientes de esa corrida).
   - Error: se vuelve a `IdleView` con el mensaje del error en rojo (el video sigue elegido).
4. **`ProcessPage`** (`QStackedWidget` interno con las tres vistas):
   - `choose_video(path)`: `composition.validated_video(config, path)`; `LectorPlacasError` → mensaje en `IdleView`.
   - `start()`: igual que `ProcessTab.start` de la spec 043 (mismo `ProcessingWorker` de `gui/processing.py`,
     `QThread`, conexión **directa** de `worker.finished` a `thread.quit`, un solo trabajo a la vez), con el perfil
     marcado; cambia a `RunningView`, emite `busy_changed(True)` y guarda el instante de inicio (`time.monotonic`).
   - Progreso: actualiza barra, contador y ETA. Galería en vivo: cuando `sightings_saved` aumenta y pasó al menos
     `LIVE_REFRESH_S` desde el último refresco, obtiene la corrida en curso (la primera de `browser.list_runs(1, 0)` si
     su estado es `RUNNING`; se recuerda su `run_id`) y `browser.search_sightings(SightingQuery(run_id=id), 200, 0)` →
     `grid.set_records` con recortes cargados como en la spec 048. `RepositoryError` en el refresco se ignora (se
     reintenta en el siguiente); no se abre diálogo.
   - `succeeded` → `DoneView` de éxito con las estadísticas del `RunResult` y un último refresco de la galería;
     `cancelled` → `DoneView` de cancelado; `failed` → `IdleView` con el error. Al recibir `finished` del hilo:
     `busy_changed(False)` y `run_finished`.
   - "Revisar … pendientes"/"Ver lecturas" → `review_requested(run_id)`; "Procesar otro video" → `IdleView` sin video.
   - `cancel`, `is_busy` y `wait_for_worker` como en la spec 043.
   - Registra solo lo que ya registra `processing.py`; nunca la ruta completa ni texto de placa.
5. **`tools_dialogs.py`**:
   - `ToolsDialog`: `setWindowTitle(TOOLS_TITLE)`, contiene un `MaintenanceTab(session)` (spec 045, sin cambios) y un
     botón "Cerrar". `set_busy` reenvía a la pestaña. Si la purga emite `data_changed`, el diálogo lo reenvía con su
     propia señal `data_changed = Signal()`.
   - `RunsDialog`: `setWindowTitle(RUNS_TITLE)`, una `NoCopyTableView` con `RunsTableModel` (spec 043/044) cargada con
     `browser.list_runs(200, 0)` y un botón "Cerrar". `RepositoryError` → etiqueta con el mensaje.
6. **`MainWindow`** (reescritura; título fijo `WINDOW_TITLE`, 1280×820):
   - Barra superior (un `QWidget` con fondo `SURFACE` y borde inferior): a la izquierda "lectorPlacas" en negrita; en
     el centro dos botones conmutables exclusivos "Procesar" y "Lecturas" (este último con el texto
     `f"Lecturas ({n} por revisar)"` si `n > 0`, actualizado con `ReadingsPage.pending_changed`); a la derecha un
     `QToolButton` "Más" con menú: "Exportar, retención y métricas…" (abre `ToolsDialog` modal) e "Historial de
     videos…" (abre `RunsDialog` modal).
   - Centro: `QStackedWidget` con `ProcessPage` y `ReadingsPage`. Página inicial: "Lecturas" si la base tiene algún
     avistamiento, si no "Procesar". `show_page` y `current_page` usan los nombres `"procesar"` y `"lecturas"`.
   - Conexiones: `ProcessPage.busy_changed` → `set_busy` → `busy_changed` → `ReadingsPage.set_busy` y el
     `ToolsDialog` abierto (si lo hay); `ProcessPage.run_finished` → `ReadingsPage.reload`;
     `ProcessPage.review_requested(run_id)` → `ReadingsPage.show_run(run_id, UNVERIFIED si hay pendientes de esa
     corrida, si no None)` y `show_page("lecturas")`; `ToolsDialog.data_changed` → `ReadingsPage.reload`.
   - Barra de estado: solo si la purga al abrir borró algo, `f"Al abrir se borraron {total} datos vencidos por la
     política de retención."` (suma de los campos de `PurgeResult`); si no, vacía.
   - `closeEvent`: igual que en la spec 043 (pregunta si hay un procesamiento en curso; "No" ignora; "Sí" cancela,
     espera y cierra), y cierra la sesión.
7. `app.py` no cambia (sigue llamando `MainWindow(session, purge)`); `QtReviewUI` desaparece de la GUI (la CLI sigue con
   `OpenCvReviewUI`). La regla de `test_gui_rules.py` sobre `setWindowTitle` se cumple usando las constantes.

## Casos borde y manejo de errores
- Soltar dos archivos o una extensión no permitida: el arrastre no se acepta.
- Video sin duración conocida: barra indeterminada y sin ETA.
- Cerrar la ventana durante el procesamiento: igual que la spec 043.
- Ningún texto de placa en títulos, logs, tooltips ni mensajes de error.

## Tests de aceptación
Sin pantalla (conftest de la spec 042). Sesión con los fakes de `tests/fixtures/fakes.py`; `composition.build_repository`,
`build_crop_store`, `build_process_video` y `sha256_file` sustituidos como en `tests/unit/gui/test_processing.py`
(caso de uso falso que reporta progreso y guarda avistamientos en el repositorio falso de la sesión). `QMessageBox` y
`QFileDialog` sustituidos; esperas con `QSignalSpy`/`QEventLoop` con límite de 5 s.

1. `test_process_page.py`:
   - `test_eta_text` (`None` con `fraction` `None` o 0,01; `elapsed=10`, `fraction=0.5` → `"quedan ~0:10"`).
   - `test_choose_invalid_video_shows_inline_error` (sin diálogo).
   - `test_choose_valid_video_shows_name_and_profiles`: nombre del archivo (no la ruta), un radio por perfil con su
     nombre amigable, el perfil por defecto marcado.
   - `test_drop_accepts_single_allowed_file_only` (eventos de arrastre construidos con `QMimeData` y URLs locales).
   - `test_start_switches_to_running_and_emits_busy`.
   - `test_success_shows_summary_and_review_button`: "Revisar N placas pendientes" y `review_requested` con el run_id.
   - `test_cancel_shows_cancelled_summary`.
   - `test_failure_returns_to_idle_with_error`.
   - `test_live_grid_refreshes_when_sightings_increase` (reloj monotónico sustituido para no esperar 1 s).
2. `test_tools_dialogs.py`: `test_tools_dialog_wraps_maintenance_and_forwards_busy`;
   `test_runs_dialog_lists_runs`; títulos iguales a las constantes.
3. `test_main_window.py` (reescritura):
   - `test_initial_page_depends_on_data` (base vacía → "procesar"; con avistamientos → "lecturas").
   - `test_nav_buttons_switch_pages` y `test_pending_badge_updates`.
   - `test_more_menu_has_tools_and_history`.
   - `test_review_requested_opens_readings_for_run`.
   - `test_busy_propagates_to_readings`.
   - `test_status_bar_only_when_purge_deleted_something`.
   - `test_close_while_busy_asks_and_can_abort` y `test_close_while_busy_cancels_and_waits` (como en la spec 043).
4. Los tests eliminados (`test_process_tab.py`, `test_sightings_tab.py`, `test_review_dialog.py`) ya no existen; el
   resto de `tests/unit/gui/` y `tests/architecture` pasa.

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- `wc -l src/lector_placas/gui/*.py`: ningún módulo pasa de 300 líneas; ninguna clase de 150.
- `grep -rn "sightings_tab\|process_tab\|review_dialog\|QtReviewUI" src tests` vacío.
- Prueba manual (la hace el operador): `uv run lector-gui`, arrastrar un video, procesarlo y revisar desde el resumen.
