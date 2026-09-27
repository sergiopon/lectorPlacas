# 043 - GUI: pestaña "Procesar" (hilo de procesamiento, progreso, cancelación e historial de corridas)

## Objetivo
Procesar un video desde la GUI sin congelar la ventana: elegir archivo y perfil, ejecutar `ProcessVideo` en un
`QThread` con su propia conexión a la BD, mostrar el avance, permitir cancelar y listar las corridas.

## Depende de
040, 041, 042.

## Archivos rectores aplicables
- ADR-015; ARQUITECTURA.md §6 (`except Exception` permitido en el trabajo del hilo), §7 (hilos y conexiones).
- reglas-seguridad.md SEG-06 (la ruta del video no va a la BD), SEG-12 (validación del video), SEG-20, SEG-26, SEG-27.

## Archivos a crear/modificar
- `src/lector_placas/gui/processing.py` (nuevo: reporter y worker)
- `src/lector_placas/gui/process_tab.py` (nuevo: pestaña y modelo de la tabla de corridas)
- `src/lector_placas/gui/main_window.py` (inserta la pestaña, estado ocupado y cierre con procesamiento en curso)
- `tests/unit/gui/test_processing.py`, `tests/unit/gui/test_process_tab.py` (nuevos)
- `tests/unit/gui/test_main_window.py` (añadir casos)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# gui/processing.py
REPORT_MIN_INTERVAL_S: Final[float] = 0.1

class QtProgressReporter:                    # implementa ProgressReporter
    def __init__(self, emit: Callable[[ProgressUpdate], None], clock: Callable[[], float] = time.monotonic) -> None: ...
    def report(self, update: ProgressUpdate) -> None: ...
    def cancel_requested(self) -> bool: ...
    def request_cancel(self) -> None: ...

@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    video: Path                               # ya validada con composition.validated_video
    profile_name: str

class ProcessingWorker(QObject):
    progress = Signal(object)                 # ProgressUpdate
    succeeded = Signal(object)                # RunResult
    cancelled = Signal()
    failed = Signal(str)                      # mensaje para el operador
    finished = Signal()                       # siempre, al final de run()
    def __init__(self, config: AppConfig, keys: KeyProvider, request: ProcessingRequest) -> None: ...
    def run(self) -> None: ...                # se conecta a QThread.started
    def request_cancel(self) -> None: ...

# gui/process_tab.py
RUNS_PAGE_SIZE: Final[int] = 50
RUN_COLUMNS: Final[tuple[str, ...]] = ("Corrida", "Inicio", "Perfil", "Estado", "Duración", "Confirmadas",
                                       "Sin verificar", "Sin lectura", "Velocidad")
class RunsTableModel(QAbstractTableModel):
    def set_runs(self, runs: Sequence[RunRecord]) -> None: ...
class ProcessTab(QWidget):
    busy_changed = Signal(bool)
    run_finished = Signal()
    def __init__(self, session: GuiSession) -> None: ...
    def is_busy(self) -> bool: ...
    def start(self, video: Path, profile_name: str) -> None: ...
    def cancel(self) -> None: ...
    def wait_for_worker(self) -> None: ...
    def refresh_runs(self) -> None: ...
```

## Comportamiento esperado
1. **`QtProgressReporter`**: guarda la cancelación en un `threading.Event`. `report` llama a `emit(update)` solo si pasó
   al menos `REPORT_MIN_INTERVAL_S` desde el último envío según `clock()` (el primer reporte siempre se envía) y nunca
   lanza. `cancel_requested` devuelve el estado del evento; `request_cancel` lo activa.
2. **`ProcessingWorker.run()`** (se ejecuta en el hilo del `QThread`):
   - Construye en el hilo **su propio** repositorio y almacén: `composition.build_repository(config, keys)`,
     `composition.build_crop_store(config, keys)`, y `composition.build_process_video(config, request.profile_name,
     repository, crop_store, SystemClock())`. No hace purga (ya la hizo la sesión).
   - Calcula `sha256_file(request.video)` (`infrastructure/input_validation.py`) en el hilo.
   - Ejecuta `use_case.execute(request.video, sha, reporter)` con un `QtProgressReporter` cuyo `emit` es
     `self.progress.emit`. Si `request_cancel()` se llamó antes de crear el reporter, el reporter nace cancelado.
   - Resultado: éxito → `succeeded.emit(result)`; `ProcessingCancelledError` → `cancelled.emit()`; otro
     `LectorPlacasError` → `failed.emit(str(error))`; cualquier otra excepción → `logger.exception(...)` y
     `failed.emit("error inesperado; revise logs/lector.log")` (único `except Exception` permitido fuera de `app.py`).
   - En `finally`: cierra el repositorio si se abrió y emite `finished`.
   - Registra `procesamiento gui inicio perfil=<p>` y `procesamiento gui fin resultado=<ok|cancelado|error>`; nunca la
     ruta completa ni texto de placa.
3. **`ProcessTab`** (pestaña "Procesar"):
   - Controles: botón "Elegir video…" que abre `QFileDialog.getOpenFileName` en
     `config.under_root(config.input.allowed_dirs[0])` con filtro `"Videos (*.mp4 *.mov …)"` construido con
     `config.input.allowed_extensions`; etiqueta con el **nombre** del archivo elegido; `QComboBox` de perfiles con las
     claves de `config.profiles` y seleccionado el de `config.profile(None)`; botones "Procesar" y "Cancelar";
     `QProgressBar`; etiqueta de estado; tabla de corridas (`QTableView` con `RunsTableModel`) y botón "Actualizar".
   - "Procesar": valida con `composition.validated_video(config, ruta)` en el hilo de la GUI; si lanza
     `LectorPlacasError`, `QMessageBox.warning` con `str(error)` y no arranca. Si valida, llama `start(video, perfil)`.
   - `start`: si ya hay un trabajo, no hace nada. Crea `QThread` y `ProcessingWorker`, `moveToThread`, conecta
     `started→run`, `finished→quit`, las señales del worker a slots de la pestaña, y arranca. Deshabilita "Elegir video",
     el combo y "Procesar"; habilita "Cancelar"; emite `busy_changed(True)`.
   - Progreso: si `update.fraction` es `None`, barra indeterminada (rango 0–0); si no, rango 0–1000 y valor
     `round(fraction * 1000)`. Etiqueta: `f"frames {frames_processed}/{frames_decoded} · avistamientos {sightings_saved}"`.
   - `cancel`: llama `worker.request_cancel()` y deshabilita "Cancelar" (la etiqueta dice "cancelando…").
   - Fin (`succeeded`): etiqueta con el mismo resumen que `cmd_process` (run_id, frames, confirmadas, sin_verificar,
     sin_lectura, velocidad). `cancelled`: "procesamiento cancelado". `failed`: `QMessageBox.warning` con el mensaje.
     En los tres casos, al recibir `finished` del hilo: restablece los controles, `busy_changed(False)`,
     `refresh_runs()` y `run_finished.emit()`.
   - `refresh_runs`: `session.browser.list_runs(RUNS_PAGE_SIZE, 0)`; `RepositoryError` → mensaje en la etiqueta de estado.
     Se llama al crear la pestaña.
   - `wait_for_worker`: si hay hilo, `thread.wait()` (bloquea hasta que termine).
4. **`RunsTableModel`**: una fila por `RunRecord` con las columnas de `RUN_COLUMNS`: `run_id`; `started_at` en hora local
   `"%Y-%m-%d %H:%M:%S"`; perfil; estado (`completed`→"completada", `failed`→"fallida", `running`→"en curso");
   duración del video `mm:ss` o "n/d"; confirmadas, sin verificar y sin lectura (o "n/d" si `None`); velocidad
   `f"{duration_ms / processing_ms:.2f}x"` o "n/d" si falta alguno o `processing_ms == 0`. Solo lectura.
5. **`MainWindow`** (modifica spec 042): reemplaza la pestaña "Procesar" por `ProcessTab(session)` en la misma posición.
   Expone `set_busy(busy: bool)` conectado a `busy_changed` (las specs 044 y 045 lo usan para deshabilitar sus acciones
   de escritura) y una señal `busy_changed = Signal(bool)` propia que reenvía la de la pestaña. `closeEvent`: si
   `ProcessTab.is_busy()`, pregunta con `QMessageBox.question` "Hay un procesamiento en curso. ¿Cancelarlo y salir?";
   "No" → `event.ignore()`; "Sí" → `cancel()`, `wait_for_worker()`, cierra la sesión y acepta.

## Casos borde y manejo de errores
- La carga de modelos no es cancelable: tras pedir cancelar, el hilo termina cuando `ProcessVideo` revisa la
  cancelación en el primer frame.
- Solo un procesamiento a la vez.
- Error de "base de datos bloqueada" al refrescar mientras el hilo escribe: se muestra en la etiqueta; el operador puede
  pulsar "Actualizar".
- Ningún texto de placa en etiquetas de esta pestaña, logs ni diálogos.

## Tests de aceptación
Sin pantalla (conftest de la spec 042), sin modelos ni GPU: se sustituyen con `monkeypatch` `composition.build_repository`,
`composition.build_crop_store`, `composition.build_process_video` y `input_validation.sha256_file` (o el nombre con que
`processing.py` lo importe) por fakes; el caso de uso falso llama a `progress.report` varias veces y consulta
`progress.cancel_requested()` entre reportes. Para esperar al hilo se usa `QSignalSpy` de `PySide6.QtTest` o un
`QEventLoop` con tiempo límite de 5 s; ningún test queda colgado. `QMessageBox` y `QFileDialog` se sustituyen.

1. `test_processing.py`:
   - `test_reporter_throttles_by_interval`: con un reloj falso, reportes a 0,00/0,05/0,12 s → se emiten el primero y el
     tercero.
   - `test_reporter_cancel_flag`.
   - `test_worker_success_emits_progress_succeeded_finished`: en ese orden relativo (`succeeded` antes de `finished`) y
     el repositorio falso quedó cerrado.
   - `test_worker_cancel_emits_cancelled`: `request_cancel()` durante la ejecución → `cancelled` y `finished`.
   - `test_worker_domain_error_emits_failed_message`: el caso de uso lanza `VideoSourceError("video dañado")` →
     `failed("video dañado")`.
   - `test_worker_unexpected_error_emits_generic_message`: lanza `RuntimeError` → `failed` con el mensaje genérico.
   - `test_worker_builds_repository_in_worker_thread`: el fake de `build_repository` registra
     `threading.get_ident()` y es distinto del hilo del test.
2. `test_process_tab.py`:
   - `test_profiles_combo_uses_config_and_default`.
   - `test_invalid_video_shows_warning_and_does_not_start`: `validated_video` lanza `InputValidationError`.
   - `test_start_disables_controls_and_emits_busy`; `test_finish_restores_controls_and_refreshes_runs` (y emite
     `run_finished`).
   - `test_progress_updates_bar`: `fraction=0.25` → valor 250; `fraction=None` → rango 0–0.
   - `test_runs_model_formats_rows`: corrida completada con estadísticas y una en curso con `None` → textos esperados.
3. `test_main_window.py` (añadir): `test_close_while_busy_asks_and_can_abort` (respuesta "No" ignora el evento y la
   sesión sigue abierta) y `test_close_while_busy_cancels_and_waits` (respuesta "Sí" cancela, espera y cierra).

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- Prueba manual (la hace el operador, no el implementador): `uv run lector-gui`, procesar un video corto y cancelar otro.
