# 067 - Web: API de acciones (procesar con progreso, decidir, exportar, purgar, métricas)

## Objetivo
Añadir a la app web de la spec 066 las acciones: procesar un video en un hilo con su propia conexión SQLCipher, seguir
el avance por Server-Sent Events y cancelarlo; decidir sobre un avistamiento; exportar a CSV; purgar por retención y
consultar las métricas de la revisión.

## Depende de
025, 026, 038, 040, 046, 066.

## Archivos rectores aplicables
- ADR-016 (decisiones 4 y 6), reglas-seguridad.md SEG-03, SEG-05, SEG-08, SEG-12, SEG-26, SEG-28.
- ARQUITECTURA.md §6: capturar `Exception` solo se permite en el cuerpo del hilo de trabajo (igual que en la GUI).

## Archivos a crear/modificar
- `src/lector_placas/web/jobs.py` (nuevo)
- `src/lector_placas/web/routes_actions.py` (nuevo)
- `src/lector_placas/web/schemas.py` (modelos nuevos)
- `src/lector_placas/web/factory.py` (parámetro `runner` y registro del router nuevo)
- `tests/unit/web/conftest.py` (fixture nueva `fake_runner`; la fixture `client` pasa `runner`)
- `tests/unit/web/test_jobs.py` (nuevo)
- `tests/unit/web/test_routes_actions.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `web/jobs.py`
- `JobRunner: TypeAlias = Callable[[Path, str, ProgressReporter], int]`: recibe el video ya validado, el nombre del
  perfil y el reporter; procesa y devuelve el `run_id`.
- `JobState: TypeAlias = Literal["running", "completed", "cancelled", "failed"]`.
- `GENERIC_ERROR_MESSAGE: Final[str] = "error inesperado; revise logs/lector.log"`.
- `@dataclass(frozen=True, slots=True) class JobSnapshot` con `job_id: str`, `state: JobState`, `run_id: int | None`,
  `progress: ProgressUpdate | None`, `message: str | None`.
- `class JobReporter` (implementa `ProgressReporter`): guarda el último `ProgressUpdate` bajo un `threading.Lock` y la
  cancelación en un `threading.Event`; métodos `report(update)`, `cancel_requested() -> bool`, `request_cancel()`,
  `latest() -> ProgressUpdate | None`.
- `class JobManager` con `__init__(self, runner: JobRunner)`, `start(self, video: Path, profile: str) -> str`,
  `snapshot(self, job_id: str) -> JobSnapshot` y `cancel(self, job_id: str) -> JobSnapshot`.
- `class JobBusyError(LectorPlacasError)` y `class JobNotFoundError(LectorPlacasError)`, definidas en este módulo.
- `def default_runner(config: AppConfig, keys: KeyProvider) -> JobRunner`.

### `web/schemas.py` (añadir; misma base `ApiModel`)
- `JobRequest`: `video: str`, `profile: str`.
- `JobOut`: `job_id: str`, `state: Literal["running", "completed", "cancelled", "failed"]`, `run_id: int | None`,
  `frames_decoded: int | None`, `frames_processed: int | None`, `position_ms: int | None`, `duration_ms: int | None`,
  `sightings_saved: int | None`, `fraction: float | None`, `message: str | None`.
- `DecisionIn`: `action: Literal["confirm", "correct", "reject", "illegible"]`, `corrected_text: str | None = None`.
- `ExportIn`: `status: Literal["unverified", "confirmed", "corrected", "rejected", "illegible"] | None = None`.
- `ExportOut`: `file: str`.
- `PurgeOut`: `crops_deleted: int`, `sightings_deleted: int`, `runs_deleted: int`, `plates_deleted: int`,
  `exports_deleted: int`, `training_deleted: int`.
- `MetricsOut`: un campo por cada campo de `ReviewMetrics` (spec 038/052), mismo nombre y tipo
  (`reason_counts: dict[str, int]`).

### `web/factory.py`
`create_app(..., session_factory: SessionFactory = open_web_session, runner: JobRunner | None = None)`: si `runner` es
`None`, usa `default_runner(config, keys)`. Crea `JobManager(runner)` en `app.state.jobs` y registra el router de
acciones.

### `web/routes_actions.py`
`router = APIRouter(prefix="/api")` con los endpoints del comportamiento 3, todos `async def`.

## Comportamiento esperado

### 1. `JobManager`
1. `start(video, profile)`: si hay un trabajo en estado `running` → `JobBusyError("ya hay un procesamiento en curso")`.
   Si no, `job_id = uuid.uuid4().hex`, crea un `JobReporter`, registra el estado `running` y lanza
   `threading.Thread(target=…, name=f"lector-job-{job_id[:8]}", daemon=True)`. Devuelve `job_id`.
2. Cuerpo del hilo: `run_id = runner(video, profile, reporter)` → estado `completed` con ese `run_id`.
   `ProcessingCancelledError` → `cancelled` (`run_id` `None`, `message` `"procesamiento cancelado"`).
   `LectorPlacasError` → `failed` con `message = str(error)`. Cualquier otra `Exception` → `logger.exception("procesamiento web error inesperado")`
   y `failed` con `message = GENERIC_ERROR_MESSAGE` (comentario en esa línea: `# permitido en trabajo del hilo, ARQUITECTURA §6`).
   Los cambios de estado se hacen bajo un `threading.Lock` del gestor.
3. `snapshot(job_id)`: copia inmutable del estado (con `progress = reporter.latest()`); id desconocido →
   `JobNotFoundError("trabajo no encontrado")`.
4. `cancel(job_id)`: `reporter.request_cancel()` y devuelve el `snapshot`; id desconocido → `JobNotFoundError`.
5. Los trabajos terminados se conservan en memoria mientras vive el proceso.

### 2. `default_runner(config, keys)`
Devuelve una función que, en el hilo: abre `repository = composition.build_repository(config, keys)`; en un `try/finally`
que siempre cierra el repositorio, crea `crop_store = composition.build_crop_store(config, keys)`,
`use_case = composition.build_process_video(config, profile, repository, crop_store, SystemClock())`,
`sha = sha256_file(video)` y devuelve `use_case.execute(video, sha, reporter).run_id`. Nunca usa la conexión de la
sesión web.

### 3. Endpoints (bajo `/api`)
| Método y ruta | Comportamiento |
|---|---|
| `POST /api/jobs` (cuerpo `JobRequest`) | Si `profile` no está en `config.profiles` → 422 `{"detail": "perfil desconocido"}`. `video = composition.validated_video(config, config.root_dir / body.video)`; `InputValidationError` o `UnsafePathError` → 422 `{"detail": "video no válido"}`. `jobs.start(video, profile)`; `JobBusyError` → 409 `{"detail": "ya hay un procesamiento en curso"}`. Respuesta 202 `JobOut` del `snapshot`. |
| `GET /api/jobs/{job_id}` | 200 `JobOut`; `JobNotFoundError` → 404 `{"detail": "trabajo no encontrado"}`. |
| `POST /api/jobs/{job_id}/cancel` | 202 `JobOut` de `cancel`; desconocido → 404 igual. |
| `GET /api/jobs/{job_id}/events` | SSE (comportamiento 4); desconocido → 404 igual (antes de empezar el flujo). |
| `POST /api/sightings/{id}/decision` (cuerpo `DecisionIn`) | `ReviewDecision(ACCIÓN, corrected_text en mayúsculas si no es None)` con `confirm→CONFIRM`, `correct→CORRECT`, `reject→REJECT`, `illegible→ILLEGIBLE`; `DecideSighting(session.repository, session.clock).execute(id, decision)`. 200 `SightingOut` del registro devuelto (con `duplicates` de `count_duplicates([id])`). `InvalidEntityError` o `ReviewError` → 422 `{"detail": "decisión inválida"}`; `SightingNotFoundError` → 404 `{"detail": "avistamiento no encontrado"}`. |
| `POST /api/export` (cuerpo `ExportIn`) | `ExportSightings(session.repository, session.export_store, session.clock).execute(ReviewStatus(status) o None)`; 200 `ExportOut(file=path.name)`. `ExportError` → 500 `{"detail": "no se pudo exportar"}`. |
| `POST /api/purge` | `composition.build_purge(config, repository, crop_store, export_store, clock).execute()`; 200 `PurgeOut` con sus campos. |
| `GET /api/metrics` | Recorre `session.repository.list_sightings(None, 500, offset)` hasta una página con menos de 500 y devuelve `MetricsOut` de `compute_review_metrics(registros)`. |

`JobOut` desde un `JobSnapshot`: `frames_decoded`, `frames_processed`, `position_ms`, `duration_ms`, `sightings_saved` y
`fraction` del `progress` (todos `None` si `progress` es `None`); `job_id`, `state`, `run_id` y `message` directos.

### 4. SSE `GET /api/jobs/{job_id}/events`
`StreamingResponse(generador, media_type="text/event-stream")`. El generador asíncrono repite:
1. `snap = jobs.snapshot(job_id)`; `data = JobOut(...).model_dump_json(by_alias=True)`.
2. Si `snap.state == "running"`: emite `f"event: progress\ndata: {data}\n\n"` y `await asyncio.sleep(0.25)`.
3. Si no: emite `f"event: done\ndata: {data}\n\n"` y termina.

## Casos borde y manejo de errores
- Solo un procesamiento a la vez. Cancelar un trabajo terminado no cambia su estado.
- `message` nunca contiene texto de placa (los errores del dominio ya cumplen SEG-26).
- Los endpoints de decisión, exportación, purga y métricas usan la conexión de la sesión (hilo del bucle de eventos).

## Tests de aceptación (en prosa)
`tests/unit/web/conftest.py` añade la fixture `fake_runner`: un objeto invocable con un `threading.Event` llamado `go`;
al llamarse, reporta `ProgressUpdate(1, 1, 100, 1000, 0)`, espera hasta 5 s a `go`, comprueba `cancel_requested()` y si es
`True` lanza `ProcessingCancelledError("cancelado")`; si no, devuelve `7`. La fixture `client` pasa
`runner=fake_runner`. Con `tmp_path`, se crea `videos/v.mp4` (bytes sintéticos) y la config de la app se copia con
`root_dir` en `tmp_path` para estos tests; `validated_video` se sustituye con `monkeypatch` en
`lector_placas.web.routes_actions` por una función que devuelve la ruta resuelta (la validación de contenido es de la
spec 007, no de esta).

`tests/unit/web/test_jobs.py` (sin HTTP):
- `test_job_completes`: `JobManager(runner)` con un runner que devuelve 7 → al terminar (esperar con
  `thread.join` vía sondeo de `snapshot` hasta 5 s) el estado es `completed` y `run_id == 7`.
- `test_job_cancelled`: runner `fake_runner`; `cancel(job_id)`, luego `go.set()` → estado `cancelled`, `message`
  `"procesamiento cancelado"`.
- `test_job_failed_domain_and_unexpected`: un runner que lanza `RepositoryError("fallo")` → `failed` con `message`
  `"fallo"`; otro que lanza `RuntimeError` → `failed` con `GENERIC_ERROR_MESSAGE`.
- `test_only_one_job`: con un trabajo `running`, `start` lanza `JobBusyError`.
- `test_unknown_job`: `snapshot("x")` y `cancel("x")` lanzan `JobNotFoundError`.
- `test_reporter_latest`: `JobReporter` sin reportes da `None`; tras `report(u)` da `u`.

`tests/unit/web/test_routes_actions.py`:
- `test_start_job_and_poll`: `POST /api/jobs` con `{"video": "videos/v.mp4", "profile": "calle_lenta"}` da 202 con
  `state: "running"` y `jobId`; tras `go.set()`, `GET /api/jobs/<id>` llega a `state: "completed"` y `runId: 7` (sondeo
  hasta 5 s).
- `test_start_job_errors`: perfil `"autopista"` → 422 `{"detail": "perfil desconocido"}`; con `validated_video`
  parcheado para lanzar `UnsafePathError` → 422 `{"detail": "video no válido"}`; un segundo `POST` con el primero en
  curso → 409.
- `test_events_stream`: con `go.set()` antes de pedirlo, `GET /api/jobs/<id>/events` devuelve `content-type`
  `text/event-stream` y un cuerpo cuyo último evento es `event: done` con `"state":"completed"`.
- `test_cancel_job`: `POST /api/jobs/<id>/cancel` da 202; tras `go.set()` el estado final es `cancelled`.
- `test_decision`: sobre un avistamiento `unverified`, `{"action": "correct", "correctedText": "xyz98l"}` da 200 con
  `status: "corrected"` y `plateText: "XYZ98L"`; `{"action": "correct"}` sin texto da 422 `{"detail": "decisión
  inválida"}`; sobre el id 999, 404.
- `test_export_purge_metrics`: `POST /api/export` con `{}` da 200 con `file` igual al nombre que devuelve
  `InMemoryExportStore`; `POST /api/purge` da 200 con las seis claves en camelCase; `GET /api/metrics` da 200 con las
  claves `precisionConfirmed`, `cer`, `reasonCounts` y `confirmedIllegible`.
- `test_unknown_job_404`: `GET /api/jobs/x`, `POST /api/jobs/x/cancel` y `GET /api/jobs/x/events` dan 404
  `{"detail": "trabajo no encontrado"}`.

## Fuera de alcance
- Comando `lector-web` y archivos estáticos (spec 068). Datos de demo (spec 069).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] El test `test_no_sync_endpoints` de la spec 066 sigue en verde con las rutas nuevas.
