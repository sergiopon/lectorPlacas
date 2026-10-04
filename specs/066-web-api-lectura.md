# 066 - Web: app FastAPI, seguridad local y API de lectura

## Objetivo
Crear la capa `web` (ADR-016): fábrica de la app FastAPI, sesión con su propia conexión SQLCipher, seguridad local
(SEG-28: `Host`, token de arranque de un solo uso → cookie de sesión, cabeceras) y los endpoints de **lectura**: videos,
perfiles, corridas, avistamientos, recorte y resumen. No hay todavía acciones (spec 067) ni comando de arranque
(spec 068).

## Depende de
041, 046, 056, 059, 061.

## Archivos rectores aplicables
- ADR-016, reglas-seguridad.md SEG-28 (todas sus cláusulas), SEG-05, SEG-06, SEG-07, SEG-15, SEG-23, SEG-26.
- ARQUITECTURA.md §2 (capa `web`, la actualiza el orquestador) y §6 (convenciones).
- docs/08-plan-legibilidad-y-web.md §4.3 y Anexo A (nombres de campo de la API).

## Archivos a crear/modificar
- `pyproject.toml` (dependencias) y `uv.lock`
- `src/lector_placas/web/__init__.py` (vacío salvo docstring)
- `src/lector_placas/web/security.py`
- `src/lector_placas/web/session.py`
- `src/lector_placas/web/schemas.py`
- `src/lector_placas/web/labels.py`
- `src/lector_placas/web/routes_read.py`
- `src/lector_placas/web/factory.py`
- `src/lector_placas/application/ports.py` (`SightingBrowser.count_duplicates`)
- `src/lector_placas/adapters/persistence/sqlcipher_browser.py`
- `tests/fixtures/fakes.py` (`count_duplicates` del fake)
- `tests/architecture/test_dependency_rule.py`
- `tests/unit/web/__init__.py` (vacío)
- `tests/unit/web/conftest.py`
- `tests/unit/web/test_security.py`
- `tests/unit/web/test_routes_read.py`
- `tests/integration/test_count_duplicates.py`

## Dependencias externas (verificadas en el JSON de PyPI el 2026-10-03, ADR-016)
- `[project] dependencies`: añadir `"fastapi==0.141.1"` y `"uvicorn==0.54.0"`.
- `[dependency-groups] dev`: añadir `"httpx2==2.13.1"` (cliente que usa `fastapi.testclient.TestClient` con Starlette
  1.7; con `httpx` Starlette 1.7 emite una advertencia de obsolescencia).
- Ejecutar `uv lock` y después `uv sync --locked`. No fijar `starlette` directamente: la resuelve `uv lock` (esperado: 1.7.0;
  el orquestador comprobó el 2026-10-03 que FastAPI 0.141.1 importa y sirve rutas, middleware, lifespan y SSE con
  Starlette 1.7.0 y `httpx2` 2.13.1). Si la suite falla por una incompatibilidad, **detente y reporta** la salida.

## Interfaces y tipos involucrados

### `application/ports.py`
`SightingBrowser` gana `count_duplicates(self, sighting_ids: Sequence[int]) -> dict[int, int]`: para cada id de
`sighting_ids` que tenga al menos un avistamiento con `duplicate_of` igual a él, el número de esos avistamientos. Los ids
sin duplicados no aparecen en el dict.

### `web/security.py`
- Constantes: `SESSION_COOKIE: Final[str] = "lector_session"`;
  `CSP: Final[str] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"`.
- `class SessionAuth` con `__init__(self, launch_token: str)`, `exchange(self, token: str) -> str | None` y
  `is_valid(self, cookie: str | None) -> bool`.
- `def allowed_hosts_for(port: int) -> frozenset[str]` → `frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})`.
- `def install_security(app: FastAPI, auth: SessionAuth, allowed_hosts: frozenset[str]) -> None`: registra el
  middleware HTTP de seguridad (comportamiento 2).

### `web/session.py`
- `@dataclass(slots=True) class WebSession` con `config: AppConfig`, `keys: KeyProvider`, `clock: Clock`,
  `repository: PlateRepository`, `browser: SightingBrowser`, `crop_store: CropStore`, `export_store: ExportStore` y
  `def close(self) -> None` (cierra el repositorio).
- `SessionFactory: TypeAlias = Callable[[AppConfig, KeyProvider], WebSession]`.
- `def open_web_session(config: AppConfig, keys: KeyProvider) -> WebSession`: igual que `gui/session.py::open_session`
  (repositorio, almacén de recortes, de exportaciones, purga inicial con `composition.build_purge(...).execute()` y
  `repository.browser()`), pero devuelve solo la sesión. Si falla un paso tras abrir el repositorio, lo cierra y
  relanza.

### `web/schemas.py` (pydantic; JSON en camelCase)
Base `class ApiModel(BaseModel)` con `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True,
frozen=True)` (`to_camel` de `pydantic.alias_generators`). Modelos (campos Python → JSON por alias):
- `VideoOut`: `name: str`, `path: str`, `size_bytes: int`.
- `ProfileOut`: `name: str`, `label: str`, `description: str`, `mode: Literal["estatico", "movil"]`, `default: bool`.
- `RunOut`: `id: int`, `video: str`, `profile: str`, `mode: Literal["estatico", "movil"] | None`, `started_at: datetime`,
  `duration_ms: int | None`, `processing_ms: int | None`, `speed_factor: float | None`, `vehicles: int | None`,
  `confirmed: int | None`, `unverified: int | None`, `status: Literal["running", "completed", "failed"]`.
- `RunPage`: `items: list[RunOut]`, `page: int`, `page_size: int`.
- `SightingOut`: `id: int`, `run_id: int`, `track_id: int`, `vehicle_type: str`, `plate_text: str`, `ocr_text: str`,
  `confidence: float`, `agreement: float`, `num_readings: int`, `status: str`, `reasons: list[str]`,
  `hidden_low_quality: bool`, `duplicates: int`, `duplicate_of: int | None`, `first_seen_ms: int`, `last_seen_ms: int`,
  `crop_url: str | None`, `created_at: datetime`, `reviewed_at: datetime | None`.
- `SightingPage`: `items: list[SightingOut]`, `total: int`, `page: int`, `page_size: int`.
- `SummaryOut`: `pending: int`.
- `ErrorOut`: `detail: str`.

### `web/labels.py`
`PROFILE_TEXT: Final[Mapping[str, tuple[str, str]]]` con exactamente:
`parqueadero` → `("Parqueadero o entrada", "Vehículos lentos o detenidos, cerca de la cámara")`;
`calle_lenta` → `("Calle con tráfico lento", "Tráfico urbano normal")`;
`calle_rapida` → `("Vía rápida", "Vehículos a mayor velocidad")`;
`patrulla` → `("Patrulla", "Cámara montada en un vehículo en movimiento")`.
`def profile_text(name: str) -> tuple[str, str]`: el valor del mapa o, si no está, `(name.replace("_", " ").capitalize(), "")`.

### `web/routes_read.py`
`router = APIRouter(prefix="/api")` con los endpoints del comportamiento 3, todos `async def`.

### `web/factory.py`
`def create_app(config: AppConfig, keys: KeyProvider, auth: SessionAuth, allowed_hosts: frozenset[str], session_factory: SessionFactory = open_web_session) -> FastAPI`.

## Comportamiento esperado

### 1. App y sesión
1. `create_app` crea `FastAPI(title="lectorPlacas", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", lifespan=…)`.
2. El `lifespan` llama a `session_factory(config, keys)`, guarda la sesión en `app.state.session`, hace `yield` y al
   salir llama a `session.close()`. Así la conexión se abre y se usa en el hilo del bucle de eventos.
3. Registra `install_security(app, auth, allowed_hosts)`, el endpoint `GET /auth` y el `router` de lectura.
4. **Todos** los endpoints son `async def`. Ningún endpoint de este paquete es `def` síncrono.
5. Un endpoint obtiene la sesión con `request.app.state.session`.

### 2. Seguridad (`install_security`, un único middleware `@app.middleware("http")`)
Para cada petición, en este orden:
1. Si `request.headers.get("host")` no está en `allowed_hosts` → respuesta JSON 400 `{"detail": "host no permitido"}`.
2. Si `request.url.path` empieza por `/api/` y `auth.is_valid(request.cookies.get(SESSION_COOKIE))` es `False` →
   respuesta JSON 401 `{"detail": "no autenticado"}`.
3. Si no, se llama al siguiente manejador.
4. A **toda** respuesta (incluidas las de los pasos 1 y 2) se le ponen las cabeceras
   `Content-Security-Policy: <CSP>`, `Referrer-Policy: no-referrer` y `X-Content-Type-Options: nosniff`; si la ruta
   empieza por `/api/`, además `Cache-Control: no-store`.

`SessionAuth`:
- `exchange(token)`: si el token de arranque aún no se ha usado y `secrets.compare_digest(token, launch_token)`, lo
  marca como usado, genera `session = secrets.token_urlsafe(32)`, la guarda y la devuelve; en cualquier otro caso
  devuelve `None`.
- `is_valid(cookie)`: `True` si `cookie` no es `None`, ya se generó una sesión y `secrets.compare_digest(cookie, session)`.

`GET /auth?token=<t>` (`async def`, fuera de `/api`): si `auth.exchange(t)` devuelve una sesión → `RedirectResponse("/",
status_code=303)` con `set_cookie(SESSION_COOKIE, session, httponly=True, samesite="strict", path="/", secure=False)`;
si no (o falta `token`) → JSON 403 `{"detail": "token inválido"}`.

### 3. Endpoints de lectura (todos `GET`, bajo `/api`)
| Ruta | Respuesta |
|---|---|
| `/api/health` | `{"status": "ok"}` |
| `/api/videos` | `list[VideoOut]` (comportamiento 4) |
| `/api/profiles` | `list[ProfileOut]` en el orden de `config.profiles`; `default` es `True` solo para `config.default_profile` |
| `/api/runs?page=<n>` | `RunPage` con `page_size` 50: `browser.list_runs(50, (page - 1) * 50)`; `page` entero ≥ 1, por defecto 1 |
| `/api/sightings?status=&q=&run=&duplicates=&page=` | `SightingPage` con `page_size` 48 (comportamiento 5) |
| `/api/sightings/{id}` | `SightingOut`, o 404 `{"detail": "avistamiento no encontrado"}` si `SightingNotFoundError` |
| `/api/sightings/{id}/crop` | PNG (comportamiento 6) |
| `/api/summary` | `SummaryOut(pending=browser.count_sightings(SightingQuery(status=ReviewStatus.UNVERIFIED)))` |

Parámetros inválidos (`page` < 1, no entero, `status` desconocido, `q` inválido, `run` < 1) → 422 `{"detail": "parámetro inválido"}`.
Para ello se registra en la app un manejador de `RequestValidationError` que responde exactamente eso, y los endpoints
lanzan `HTTPException(422, "parámetro inválido")` en sus validaciones propias. Ningún `detail` contiene texto de placa.

### 4. Videos
Para cada directorio de `config.input.allowed_dirs`, en su orden, `d = config.under_root(directorio)`; si `d` no existe
se ignora. Se listan los archivos regulares de `d` (**no recursivo**, `sorted(d.iterdir())`) cuya `suffix.lower()` está
en `config.input.allowed_extensions`. Cada uno da `VideoOut(name=archivo.name,
path=archivo.relative_to(config.root_dir).as_posix(), size_bytes=archivo.stat().st_size)`.

### 5. Avistamientos
- `status`: uno de `unverified`, `confirmed`, `corrected`, `rejected`, `illegible`, o ausente.
- `q`: se convierte con `.upper()`; debe cumplir `^[A-Z0-9]{1,10}$`; se usa como `plate_prefix`.
- `run`: entero ≥ 1 → `run_id`. `duplicates`: `true`/`false` (por defecto `false`) → `include_duplicates`.
- `items = browser.search_sightings(query, 48, (page - 1) * 48)`; `total = browser.count_sightings(query)`;
  `dups = browser.count_duplicates([r.sighting_id for r in items])`.
- `SightingOut` desde un `SightingRecord`: `id = sighting_id`; `vehicle_type`, `status` y cada razón por `.value`;
  `hidden_low_quality = any(r.value.startswith("predicted_") for r in reasons)`; `duplicates = dups.get(id, 0)`;
  `crop_url = f"/api/sightings/{id}/crop"` si `crop_ref` no es `None`, si no `None`; el resto, copia directa.
  `GET /api/sightings/{id}` usa `repository.get_sighting(id)` y `count_duplicates([id])`.

### 6. Recorte
`repository.get_sighting(id)`; si no existe → 404 `{"detail": "avistamiento no encontrado"}`; si `crop_ref is None` o
`crop_store.load` lanza `CropNotFoundError` → 404 `{"detail": "recorte no disponible"}`. Si no, `cv2.imencode(".png",
imagen)` (si falla → 500 `{"detail": "no se pudo codificar el recorte"}`) y `Response(content=bytes, media_type="image/png")`.
Nada se escribe a disco.

### 7. Corridas
`RunOut` desde un `RunRecord`: `id = run_id`; `video = f"Video {run_id}"` (SEG-06: el nombre del archivo no está en la
BD); `mode` = `config.profiles[profile].mode` si el perfil existe en la configuración actual, si no `None`;
`speed_factor = duration_ms / processing_ms` si ambos no son `None` y `processing_ms > 0`, si no `None`;
`vehicles = confirmed + unverified + tracks_without_reading` si los tres no son `None`, si no `None`;
`confirmed = sightings_confirmed`; `unverified = sightings_unverified`; `status = status.value`.

### 8. `count_duplicates`
- SQLCipher: si la lista está vacía devuelve `{}`; si no,
  `SELECT duplicate_of, count(*) FROM sightings WHERE duplicate_of IN (SELECT value FROM json_each(?)) GROUP BY duplicate_of`
  con el parámetro `json.dumps(list(sighting_ids))`; `sqlcipher.Error` → `RepositoryError("count_duplicates falló")`.
- Fake: cuenta en `self.records` los registros con `duplicate_of` en la lista.

### 9. Regla de dependencias (`tests/architecture/test_dependency_rule.py`)
- Añadir `"lector_placas.web"` a la tupla prohibida de cada capa existente en `FORBIDDEN_PREFIXES` y añadir las claves
  `"gui": ("lector_placas.web",)` y `"web": ("lector_placas.gui", "lector_placas.datasets")`.
- Test nuevo `test_web_imports_from_cli_only_composition`: copia de `test_gui_imports_from_cli_only_composition` sobre
  `_files("web")`.
- Test nuevo `test_only_web_imports_http_server_packages`: ningún archivo fuera de `web/` importa `fastapi`, `starlette`
  ni `uvicorn` (raíz del nombre importado).

## Casos borde y manejo de errores
- Segundo uso del mismo token de arranque → 403, aunque el primero haya funcionado.
- Cookie de otra sesión o vacía → 401 en `/api/*`. `/auth` no exige cookie.
- `Host` ausente → 400.
- El JSON de las respuestas puede contener texto de placa (es la interfaz); los logs y los `detail`, nunca.

## Tests de aceptación (en prosa)
Fixtures sintéticos. `tests/unit/web/conftest.py` define:
- la fixture `config` = `load_config(<raíz>/config/lector.yaml)`;
- una función `make_session(config, keys)` que devuelve un `WebSession` con `InMemoryPlateRepository` (su `browser()`
  es él mismo), `InMemoryCropStore`, `InMemoryExportStore`, `FakeClock()` y `FakeKeyProvider()`, y guarda el repositorio
  y el almacén de recortes en atributos accesibles al test;
- la fixture `client`: `create_app(config, FakeKeyProvider(), SessionAuth("arranque"), allowed_hosts_for(8765),
  session_factory=make_session)` dentro de `with TestClient(app, base_url="http://127.0.0.1:8765") as c`, que antes de
  devolverlo hace `c.get("/auth", params={"token": "arranque"}, follow_redirects=False)` (queda autenticado).

`tests/unit/web/test_security.py`:
- `test_auth_exchanges_token_once`: con un cliente sin autenticar, `/auth?token=arranque` da 303 a `/` y
  `Set-Cookie` contiene `lector_session=`, `HttpOnly`, `SameSite=strict` y `Path=/`; repetirlo da 403
  `{"detail": "token inválido"}`.
- `test_wrong_token_is_rejected`: `/auth?token=otro` da 403; `/auth` sin token da 403.
- `test_api_requires_cookie`: sin autenticar, `GET /api/health` da 401 `{"detail": "no autenticado"}`; autenticado, 200
  `{"status": "ok"}`; con la cookie cambiada por `x`, 401.
- `test_host_is_checked`: con `headers={"host": "evil.example:8765"}` da 400 `{"detail": "host no permitido"}`; con
  `localhost:8765`, 200.
- `test_security_headers`: la respuesta de `/api/health` tiene `Content-Security-Policy` igual a `CSP`,
  `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` y `Cache-Control: no-store`; la de un 401 también
  tiene las tres primeras.
- `test_no_sync_endpoints`: recorre `app.routes`; toda ruta con `endpoint` tiene `inspect.iscoroutinefunction(endpoint)`
  verdadero.

`tests/unit/web/test_routes_read.py`:
- `test_profiles`: devuelve 4 perfiles en el orden de la config; `calle_lenta` tiene `default: true`; `patrulla` tiene
  `mode: "movil"`, `label: "Patrulla"`; las claves JSON son exactamente `name`, `label`, `description`, `mode`,
  `default`.
- `test_videos_lists_allowed_files`: crea su propia app y cliente autenticado (igual que la fixture `client`) con una
  copia de la configuración cuyo `root_dir` es `tmp_path` (`config.model_copy(update={"root_dir": tmp_path})`), y `tmp_path/videos` con `a.mp4` (3 bytes), `b.txt` y la carpeta
  `sub/c.mp4`, devuelve solo `[{"name": "a.mp4", "path": "videos/a.mp4", "sizeBytes": 3}]`.
- `test_sightings_page_and_fields`: con 3 avistamientos sintéticos guardados en el repositorio fake (uno con recorte),
  `GET /api/sightings` da `total: 3`, `pageSize: 48`, los `items` en orden de `id` descendente y, en el que tiene
  recorte, `cropUrl: "/api/sightings/<id>/crop"`, `hiddenLowQuality: false`, `duplicates: 0`, y las claves `runId`,
  `plateText`, `ocrText`, `numReadings`, `firstSeenMs`, `lastSeenMs`, `reviewedAt` presentes.
- `test_sightings_filters`: `status=confirmed` devuelve solo los confirmados; `q=abc` (minúsculas) filtra por prefijo
  `ABC`; `q=AB-1` da 422 `{"detail": "parámetro inválido"}`; `status=otro` da 422; `page=0` da 422.
- `test_duplicates_hidden_and_counted`: con `mark_duplicates([(2, 1)])` en el fake, la lista por defecto no incluye el 2
  y el 1 trae `duplicates: 1`; con `duplicates=true` aparecen los dos y el 2 trae `duplicateOf: 1`.
- `test_sighting_detail_and_404`: `GET /api/sightings/1` da el detalle; `GET /api/sightings/999` da 404
  `{"detail": "avistamiento no encontrado"}`.
- `test_crop_png_in_memory`: el recorte del avistamiento con imagen da 200, `content-type: image/png`,
  `cache-control: no-store` y bytes que `cv2.imdecode` convierte en la imagen original; el de uno sin recorte da 404
  `{"detail": "recorte no disponible"}`.
- `test_runs_and_summary`: con una corrida de perfil `calle_lenta` iniciada con `VideoInfo(640, 480, 0, 10000, 10.0,
  "h264")` y terminada con `RunStats(10, 10, 4, 2, 1, 1, 5000, 10000)`, `GET /api/runs` da un item con `video: "Video 1"`, `speedFactor: 2.0`, `vehicles: 4`,
  `mode` según el perfil de la corrida (`"estatico"` si es `calle_lenta`); `GET /api/summary` da `{"pending": n}` con el
  número de `unverified` no duplicados.

`tests/integration/test_count_duplicates.py` (SQLCipher real):
- `test_count_duplicates`: tres avistamientos; `mark_duplicates([(2, 1), (3, 1)])`; `count_duplicates([1, 2, 3])` es
  `{1: 2}`; `count_duplicates([])` es `{}`.

Además, los tests de arquitectura modificados (comportamiento 9) pasan.

## Fuera de alcance
- Acciones (procesar, decidir, exportar, purgar, métricas): spec 067. Arranque `lector-web` y estáticos: spec 068.
- Filtro `hidden` de "ocultas por baja calidad": spec 064.

## Definition of Done
- [ ] `uv lock` y `uv sync --locked` sin errores; `uv.lock` incluido en el cambio.
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `uv run pip-audit` sin vulnerabilidades (si reporta alguna, detente y reporta la salida).
- [ ] `grep -rn "def " src/lector_placas/web/routes_read.py | grep -v "async def"` solo muestra funciones auxiliares
      que no están decoradas como rutas.
