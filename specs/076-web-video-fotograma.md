# 076 - Web: video original, fotograma completo, conteos y ajustes para el frontend

## Objetivo
Dar a la API lo que pide el frontend diseñado en Figma Make (2026-10-04) y que hoy no existe:
1. **Ir al video** (botón "Ir al video", tecla V): servir el video original de una corrida para que el navegador lo abra
   en el segundo en que aparece la placa. El video se localiza por su SHA-256 (SEG-06: la BD no guarda ruta ni nombre).
2. **Captura completa** (tecla F): el fotograma completo del momento del avistamiento, decodificado en memoria.
3. Conteos por pestaña de la vista de lecturas, métricas por corrida, ajustes de retención y duración de cada video.

Nada de esto escribe a disco ni guarda la ruta del video en la BD.

## Depende de
066, 067, 068.

## Archivos rectores aplicables
- ADR-016; reglas-seguridad.md SEG-06, SEG-07, SEG-28.
- ARQUITECTURA.md §2 (regla de dependencias), §6 (errores).
- docs/02-contratos.md (puerto nuevo `FrameGrabber`).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py` (puerto `FrameGrabber`)
- `src/lector_placas/adapters/video/pyav_frame_grabber.py` (nuevo)
- `src/lector_placas/cli/composition.py` (`build_video_source_factory`, `build_frame_grabber`)
- `src/lector_placas/web/media.py` (nuevo)
- `src/lector_placas/web/routes_media.py` (nuevo)
- `src/lector_placas/web/schemas.py`
- `src/lector_placas/web/routes_read.py` (`/api/videos`)
- `src/lector_placas/web/factory.py` (crea `app.state.media` y registra el router nuevo)
- `tests/unit/adapters/test_pyav_frame_grabber.py` (nuevo)
- `tests/unit/web/test_media.py` (nuevo)
- `tests/unit/web/test_routes_media.py` (nuevo)
- `tests/unit/web/test_routes_read.py` (un cambio de expectativa)

## Dependencias externas
Ninguna nueva. Verificado en el código instalado (2026-10-04):
- PyAV 18.1.0: `InputContainer.seek(offset, *, backward=True, any_frame=False, stream=None)`, con `offset` en
  `stream.time_base` cuando se pasa `stream`.
- Starlette 1.7.0: `starlette.responses.FileResponse` atiende cabeceras `Range` (206 y `Accept-Ranges: bytes`);
  `starlette.concurrency.run_in_threadpool(func, *args)`.

## Interfaces y tipos involucrados

### `application/ports.py`
```
class FrameGrabber(Protocol):
    def grab(self, path: Path, timestamp_ms: int) -> ImageBGR: ...
```
Docstring con el formato de los demás puertos. Precondiciones: `path` es un video ya localizado por `VideoLocator`;
`timestamp_ms >= 0`. Postcondiciones: imagen BGR upright (rotación aplicada) del primer frame cuyo timestamp (mismo
cálculo que `PyAVVideoSource`: relativo al PTS del primer frame) es `>= timestamp_ms`; si el video termina antes, el
último frame decodificado. Errores: `VideoSourceError`.

### `adapters/video/pyav_frame_grabber.py`
`class PyAVFrameGrabber` con `grab(self, path: Path, timestamp_ms: int) -> ImageBGR`.

### `cli/composition.py`
- `def build_video_source_factory() -> VideoSourceFactory`: devuelve `PyAVVideoSourceFactory()`. La línea de
  `build_process_video` que hoy crea `PyAVVideoSourceFactory()` pasa a llamar a esta función.
- `def build_frame_grabber() -> FrameGrabber`: devuelve `PyAVFrameGrabber()`.

### `web/media.py`
- `class VideoLocator` con `__init__(self, config: AppConfig)`, `candidates(self) -> list[Path]` y
  `find(self, sha256: str) -> Path | None`.
- `@dataclass(frozen=True, slots=True) class MediaServices` con `locator: VideoLocator`, `grabber: FrameGrabber` y
  `sources: VideoSourceFactory`.
- `VIDEO_MEDIA_TYPES: Final[Mapping[str, str]]` con exactamente: `.mp4` → `video/mp4`, `.m4v` → `video/mp4`,
  `.mov` → `video/quicktime`, `.mkv` → `video/x-matroska`, `.avi` → `video/x-msvideo`, `.webm` → `video/webm`.
- `def probe_duration_ms(sources: VideoSourceFactory, path: Path) -> int | None`.

### `web/schemas.py` (añadir; base `ApiModel`)
- `VideoOut` gana, **al final**, `duration_ms: int | None`.
- `SightingCountsOut`: `unverified: int`, `confirmed: int`, `corrected: int`, `rejected: int`, `illegible: int`,
  `all: int`, `hidden: int`.
- `RunMetricsOut`: `run_id: int`, `legible: int`, `illegible: int`, `rejected: int`, `precision: float | None`,
  `cer: float | None`.
- `SettingsOut`: `crops_days: int`, `records_days: int`, `training_days: int`.

### `web/routes_media.py`
`router = APIRouter(prefix="/api")` con los endpoints del comportamiento 4, todos `async def`.

### `web/factory.py`
`create_app` (firma sin cambios) asigna, antes de registrar routers,
`app.state.media = MediaServices(VideoLocator(config), composition.build_frame_grabber(), composition.build_video_source_factory())`
y registra `routes_media.router` después de los routers existentes y antes de `_mount_frontend`. Los tests sustituyen
`app.state.media` por servicios falsos tras crear la app.

## Comportamiento esperado

### 1. `PyAVFrameGrabber.grab(path, timestamp_ms)`
1. `container = av.open(str(path), mode="r")`; `av.error.FFmpegError` u `OSError` →
   `VideoSourceError("no se pudo abrir el video")`. Sin stream de video → cerrar y
   `VideoSourceError("el archivo no contiene video")`. Todo lo siguiente va en `try/finally` con `container.close()`.
2. `stream = container.streams.video[0]`; decodifica el primer frame con `next(container.decode(stream))`
   (`StopIteration` o `FFmpegError` → `VideoSourceError("el video no tiene frames decodificables")`; PTS `None` → el
   mismo error). `first_pts = primer.pts`; `steps = rotation_steps(primer.rotation)` (de `pyav_source`).
3. Si `timestamp_ms == 0` → devuelve el primer frame convertido (paso 5).
4. Si no: `container.seek(first_pts + int(timestamp_ms / 1000 / stream.time_base), backward=True, any_frame=False, stream=stream)`;
   recorre `container.decode(stream)`; ignora frames con `pts None`; para cada uno,
   `ts = round((pts - first_pts) * time_base * 1000)` (con `time_base = frame.time_base or stream.time_base`); guarda el
   último; si `ts >= timestamp_ms` lo devuelve convertido. Si el bucle termina, devuelve el último guardado o, si no hubo
   ninguno, el primer frame. `FFmpegError` durante la decodificación → `VideoSourceError("error decodificando el video")`.
5. Conversión: `frame.to_ndarray(format="bgr24")` y, si `steps != 0`,
   `np.ascontiguousarray(np.rot90(imagen, k=steps))`.

### 2. `VideoLocator`
- `candidates()`: misma regla que `_list_videos` de la spec 066 (directorios de `config.input.allowed_dirs` en orden,
  `config.under_root`, no recursivo, `sorted(iterdir())`, archivos regulares con `suffix.lower()` en
  `config.input.allowed_extensions`). `_list_videos` pasa a usar `candidates()`.
- `find(sha256)`: para cada candidato, en orden, clave `(str(ruta), st_size, st_mtime_ns)`; si la clave no está en la
  caché, calcula `sha256_file(ruta)` (de `infrastructure.input_validation`) y la guarda; si coincide con `sha256`,
  devuelve la ruta. Si ninguno coincide, `None`. La caché es un `dict` en memoria protegido por un `threading.Lock`
  (el cálculo del hash se hace fuera del cerrojo); nunca se escribe a disco ni se registra la ruta en el log.

### 3. `probe_duration_ms(sources, path)`
`source = sources.open(path)`; devuelve `source.info().duration_ms` y cierra la fuente en `finally`.
`VideoSourceError` → `None`.

### 4. Endpoints (bajo `/api`, todos `async def`)
Las operaciones bloqueantes (`find`, `grab`, `probe_duration_ms`) se ejecutan con `await run_in_threadpool(...)`.
`media = request.app.state.media`.

| Método y ruta | Comportamiento |
|---|---|
| `GET /api/runs/{run_id}/video` | `sha = session.repository.run_video_hashes().get(run_id)`; si `None` → 404 `{"detail": "video no disponible"}`. `path = await run_in_threadpool(media.locator.find, sha)`; si `None` → el mismo 404. Si no, `FileResponse(path, media_type=VIDEO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))` **sin** `filename` (no se expone el nombre en `Content-Disposition`). |
| `GET /api/sightings/{id}/frame` | `record = session.repository.get_sighting(id)`; `SightingNotFoundError` → 404 `{"detail": "avistamiento no encontrado"}`. `sha` de `run_video_hashes()` para `record.run_id` y `path` como arriba; si falta cualquiera → 404 `{"detail": "video no disponible"}`. `t = (record.first_seen_ms + record.last_seen_ms) // 2`; `imagen = await run_in_threadpool(media.grabber.grab, path, t)`; `VideoSourceError` → 404 `{"detail": "fotograma no disponible"}`. `cv2.imencode(".png", imagen)` (si falla → 500 `{"detail": "no se pudo codificar el fotograma"}`) y `Response(content=bytes, media_type="image/png", headers={"X-Frame-Timestamp-Ms": str(t)})`. Nada se escribe a disco. |
| `GET /api/sighting-counts?q=&run=&duplicates=` | Mismos parámetros y validación que `/api/sightings` (spec 066) salvo `status`, `hidden` y `page`, que no existen aquí. Con `count = browser.count_sightings` y la consulta base `SightingQuery(plate_prefix, run_id, include_duplicates)`: cada estado → `count(replace(base, status=E, low_quality="exclude"))`; `all` → `count(replace(base, low_quality="exclude"))`; `hidden` → `count(replace(base, low_quality="only"))`. Responde `SightingCountsOut`. (La ruta no cuelga de `/api/sightings/` para no chocar con `/api/sightings/{id}`.) |
| `GET /api/metrics/runs` | Recorre `session.repository.list_sightings(None, 500, offset)` como `GET /api/metrics` (spec 067), agrupa por `run_id` (orden ascendente) y para cada grupo `m = compute_review_metrics(grupo)` → `RunMetricsOut(run_id, legible = nº de registros con estado CONFIRMED o CORRECTED, illegible = nº ILLEGIBLE, rejected = nº REJECTED, precision = m.precision_confirmed, cer = m.cer)`. Responde la lista (vacía si no hay registros). |
| `GET /api/settings` | `SettingsOut` con los tres campos de `config.retention`. |

`GET /api/videos` (spec 066) añade a cada `VideoOut` `duration_ms = probe_duration_ms(media.sources, archivo)`; el
listado completo se ejecuta en `run_in_threadpool`.

### 5. Cabeceras
El middleware de la spec 066 ya pone `Cache-Control: no-store` y las demás cabeceras de SEG-28 en todo `/api/*`, incluidos
el video y el fotograma. No se añade nada.

## Casos borde y manejo de errores
- Video movido, renombrado o borrado: si sigue en un directorio permitido con el mismo contenido, se encuentra (por
  hash); si no, 404 `video no disponible` y el frontend lo explica.
- Primer `find` de un video grande: tarda lo que tarde el SHA-256 (se hace en un hilo; el resto de la API sigue
  respondiendo). Las siguientes peticiones usan la caché mientras no cambien tamaño ni fecha.
- Los mensajes de error no llevan nombres de archivo, rutas ni texto de placa.

## Tests de aceptación (en prosa)
Fixtures sintéticos. Los videos de prueba se generan en `tmp_path` con PyAV (como hacen los tests de
`pyav_source`): 30 frames de 64×48 a 10 fps, cada frame de un color plano distinto (frame `i` con valor `i * 8` en los
tres canales).

**Test existente que cambia de expectativa (solo este):**
- `tests/unit/web/test_routes_read.py::test_videos_lists_allowed_files` (spec 066): cada elemento tiene además la clave
  `durationMs` (con archivos que no son video real, su valor es `null`).

`tests/unit/adapters/test_pyav_frame_grabber.py`:
- `test_grab_first_and_middle_frame`: `grab(video, 0)` devuelve forma `(48, 64, 3)` con el valor del frame 0;
  `grab(video, 1500)` devuelve el del frame 15 (tolerancia ±4 en el valor del píxel por la compresión).
- `test_grab_past_end_returns_last`: `grab(video, 60_000)` devuelve el valor del frame 29 (misma tolerancia).
- `test_grab_errors`: un archivo con bytes aleatorios lanza `VideoSourceError` con el mensaje
  `no se pudo abrir el video` o `el archivo no contiene video`; el mensaje no contiene el nombre del archivo.

`tests/unit/web/test_media.py`:
- `test_locator_finds_by_hash_and_caches`: dos videos en `tmp_path/videos`; `find(sha del segundo)` devuelve su ruta;
  con `sha256_file` parcheado en `lector_placas.web.media` para contar llamadas, un segundo `find` del mismo hash no
  vuelve a calcular ningún hash; un hash inexistente da `None`.
- `test_locator_ignores_other_extensions_and_subdirs`: un `.txt` y un video en un subdirectorio no son candidatos.
- `test_probe_duration`: con el video sintético da 3000 ± 100; con un archivo que no es video da `None`.

`tests/unit/web/test_routes_media.py` (cliente autenticado como en la spec 066; `app.state.media` sustituido por
`MediaServices` con un `VideoLocator` real sobre `tmp_path`, un grabber falso que devuelve una imagen 48×64 y registra
`(path, t)`, y la fábrica real de PyAV; una corrida 1 creada en el repositorio falso con `start_run` cuyo `video_sha256` es el SHA-256 del video de `tmp_path/videos/v.mp4`):
- `test_video_full_and_range`: `GET /api/runs/1/video` da 200, `content-type` `video/mp4`, cuerpo igual al archivo y
  sin cabecera `content-disposition`; con `Range: bytes=0-99` da 206 y 100 bytes; `GET /api/runs/2/video` da 404
  `{"detail": "video no disponible"}`.
- `test_frame`: un avistamiento con `first_seen_ms=1000` y `last_seen_ms=2000` en la corrida 1 → 200 `image/png`,
  cabecera `x-frame-timestamp-ms: 1500` y el grabber recibió `t == 1500`; id inexistente → 404 `avistamiento no
  encontrado`; con el video borrado del disco → 404 `video no disponible`; con el grabber lanzando `VideoSourceError` →
  404 `fotograma no disponible`.
- `test_counts`: con los avistamientos A–D de la spec 064 (A `confirmed`; B, C, D `unverified`; C y D con razones
  `predicted_*`), `GET /api/sighting-counts` da `{"unverified": 1, "confirmed": 1, "corrected": 0, "rejected": 0,
  "illegible": 0, "all": 2, "hidden": 2}`; `q=Ñ` da 422 `{"detail": "parámetro inválido"}`.
- `test_metrics_by_run`: con registros de dos corridas da una lista de 2 elementos ordenada por `runId` con las claves
  `runId`, `legible`, `illegible`, `rejected`, `precision`, `cer`; sin registros, `[]`.
- `test_settings`: `GET /api/settings` da `{"cropsDays": …, "recordsDays": …, "trainingDays": …}` con los valores de la
  configuración usada.
- `test_media_requires_session`: sin cookie, las cinco rutas nuevas dan 401.

## Fuera de alcance
- Guardar la caja de la placa en el fotograma (el frontend no dibuja recuadro; `box` queda para una spec futura con
  migración de esquema).
- Recorrer subdirectorios o directorios fuera de `allowed_dirs`.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde; solo cambia el test listado.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios, sin `# noqa` nuevos.
- [ ] `grep -rn "def " src/lector_placas/web/routes_media.py | grep -v "async def"` solo muestra funciones auxiliares
      privadas.
