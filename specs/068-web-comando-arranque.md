# 068 - Web: comando `lector-web`, puerto local y frontend compilado

## Objetivo
Añadir el punto de entrada `lector-web`: prepara configuración, logging y clave (antes de la guardia de red), bloquea la
red, elige un puerto libre de `127.0.0.1`, crea la app de las specs 066–067, sirve el frontend compilado
(`frontend/dist/`) si existe y abre el navegador con el token de arranque.

## Depende de
066, 067.

## Archivos rectores aplicables
- ADR-016 (decisiones 2, 3, 5 y 7), reglas-seguridad.md SEG-04, SEG-20, SEG-28.
- ARQUITECTURA.md §6 (`except Exception` solo en el nivel más alto del punto de entrada, como en `gui/app.py`).

## Archivos a crear/modificar
- `pyproject.toml` (`[project.scripts]`)
- `src/lector_placas/web/app.py` (nuevo)
- `src/lector_placas/web/factory.py` (parámetro `static_dir`)
- `tests/unit/web/test_app.py` (nuevo)
- `tests/unit/web/test_static.py` (nuevo)

## Dependencias externas
Ninguna nueva. API de Uvicorn 0.54.0 verificada en su código fuente (2026-10-03): `uvicorn.Config(app, host, port,
lifespan, log_level, access_log, server_header, date_header)` y `uvicorn.Server(config).run(sockets=[...])`. Starlette
1.7.0: `starlette.staticfiles.StaticFiles(directory=..., html=True)`.

## Interfaces y tipos involucrados

### `pyproject.toml`
En `[project.scripts]`, añadir `lector-web = "lector_placas.web.app:main"` después de `lector-gui`.

### `web/factory.py`
`create_app(..., runner: JobRunner | None = None, static_dir: Path | None = None)`:
- La firma queda con 7 parámetros: única excepción permitida, `# noqa: PLR0913, PLR0917 — firma fijada por la spec 068`
  en la línea `def create_app(` (precedente: `purge_expired.py`, spec 055). El montaje del frontend va en una función
  privada `_mount_frontend(app, static_dir)` para no pasar de 20 sentencias.
- Si `static_dir` no es `None` y `(static_dir / "index.html").is_file()`: tras registrar los routers y `/auth`,
  `app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")`.
- Si no: registra `GET /` (`async def`) que devuelve `HTMLResponse(NO_FRONTEND_HTML)` con
  `NO_FRONTEND_HTML: Final[str] = "<!doctype html><html lang=\"es\"><meta charset=\"utf-8\"><title>lectorPlacas</title><p>Frontend no compilado. Ejecute <code>npm ci &amp;&amp; npm run build</code> en <code>frontend/</code> y reinicie <code>lector-web</code>.</p></html>"`.

### `web/app.py`
- Constantes: `DEFAULT_CONFIG_PATH: Final[Path] = Path("config/lector.yaml")`, `LOG_FILENAME: Final[str] = "lector.log"`,
  `HOST: Final[str] = "127.0.0.1"`, `FRONTEND_DIST: Final[Path] = Path("frontend/dist")`,
  `KEY_HINT: Final[str] = "Cree la clave con: lector key init"`.
- `def parse_args(argv: Sequence[str] | None) -> argparse.Namespace` con `prog="lector-web"` y las opciones
  `--config` (`Path`, por defecto `DEFAULT_CONFIG_PATH`), `--port` (`int`, por defecto `0`) y `--no-browser`
  (`store_true`).
- `def bind_socket(port: int) -> socket.socket`.
- `def launch_url(port: int, token: str) -> str` → `f"http://{HOST}:{port}/auth?token={token}"`.
- `def main(argv: Sequence[str] | None = None) -> int`.

## Comportamiento esperado

### 1. `bind_socket(port)`
Crea `socket.socket(socket.AF_INET, socket.SOCK_STREAM)`, `setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)`,
`bind((HOST, port))` y lo devuelve. Con `port=0` el sistema asigna uno libre. Si `port` no está en `[0, 65535]` →
`ValueError(f"puerto inválido: {port}")` antes de crear el socket. Un `OSError` del `bind` (puerto ocupado) se propaga.

### 2. `main(argv)`, en este orden
1. `os.umask(0o077)` (primera instrucción).
2. `args = parse_args(argv)`.
3. Dentro de `try`: `config = load_config(args.config)`;
   `configure_logging(config.logging.level, config.under_root(config.paths.log_dir) / LOG_FILENAME)`;
   `keys = composition.build_key_provider(False)`; `keys.master_key()`. Un `LectorPlacasError` aquí →
   escribe en `sys.stderr` `f"lector-web: {error}\n"` (y, si es `KeyUnavailableError`, además `f"{KEY_HINT}\n"`) y
   devuelve `1`.
4. `network_guard.block_network()`.
5. `sock = bind_socket(args.port)`; `OSError` o `ValueError` → `sys.stderr` `f"lector-web: no se pudo abrir el puerto {args.port}\n"`
   y devuelve `1`. `port = sock.getsockname()[1]`.
6. `token = secrets.token_urlsafe(32)`; `auth = SessionAuth(token)`;
   `app = create_app(config, keys, auth, allowed_hosts_for(port), static_dir=config.under_root(FRONTEND_DIST))`.
7. `url = launch_url(port, token)`; escribe en `sys.stdout` `f"lectorPlacas web en http://{HOST}:{port}/\nAbra: {url}\n"`
   (el token solo sale por la terminal del operador; nunca va al log).
8. Si no es `--no-browser`: `webbrowser.open(url)` (su resultado se ignora).
9. `server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, lifespan="on", log_level="warning",
   access_log=False, server_header=False, date_header=False))`; `server.run(sockets=[sock])`. Al volver, `sock.close()`
   y devuelve `0`.
10. Todo el cuerpo de los pasos 4–9 va dentro de un `try` cuyo `except Exception:` (comentario
    `# último nivel permitido para except Exception, ARQUITECTURA §6`) hace `logger.exception("error inesperado")` y
    devuelve `1`.

## Casos borde y manejo de errores
- `--port 8765` ocupado → código 1 y el mensaje del paso 5.
- La guardia de red se activa antes de abrir el socket y de crear la app; abrir el navegador lanza un proceso externo y
  no usa `connect` en este proceso.
- Ningún log contiene el token ni texto de placa.

## Tests de aceptación (en prosa)
`tests/unit/web/test_app.py` (sin servidor real ni navegador):
- `test_parse_args_defaults`: `parse_args([])` da `config == Path("config/lector.yaml")`, `port == 0`,
  `no_browser is False`; `parse_args(["--port", "9000", "--no-browser"])` da `9000` y `True`.
- `test_bind_socket_is_loopback`: `bind_socket(0)` devuelve un socket cuyo `getsockname()[0] == "127.0.0.1"` y puerto
  > 0; se cierra al final. `bind_socket(70000)` lanza `ValueError` con el mensaje `puerto inválido: 70000`.
- `test_launch_url`: `launch_url(8765, "abc")` es `http://127.0.0.1:8765/auth?token=abc`.
- `test_main_happy_path`: con `monkeypatch` de `lector_placas.web.app.configure_logging` (no hace nada, para no escribir
  en `logs/`), `lector_placas.web.app.composition.build_key_provider` (devuelve `FakeKeyProvider()`), `lector_placas.web.app.network_guard.block_network` (registra que se llamó),
  `lector_placas.web.app.create_app` (registra sus argumentos y devuelve un objeto cualquiera),
  `lector_placas.web.app.webbrowser.open` (registra la URL) y `lector_placas.web.app.uvicorn.Server` (clase falsa cuyo
  `run(sockets)` registra el host y el puerto del socket y vuelve); `main(["--no-browser"])` devuelve 0, llamó a
  `block_network` antes que a `create_app`, el socket es de `127.0.0.1`, `webbrowser.open` no se llamó, la salida
  estándar contiene `Abra: http://127.0.0.1:` y `/auth?token=`, y `create_app` recibió `static_dir` igual a
  `<raíz del repo>/frontend/dist` (la configuración usada es la real, `config/lector.yaml`). Con `main([])`, `webbrowser.open` se llamó una vez con la URL de la salida.
- `test_uvicorn_config_flags`: en el mismo escenario, el `uvicorn.Config` recibido (registrado por un `uvicorn.Config`
  falso parcheado) tiene `host == "127.0.0.1"`, `access_log is False`, `server_header is False`,
  `date_header is False` y `lifespan == "on"`.
- `test_main_key_missing`: con `build_key_provider` devolviendo un proveedor cuyo `master_key()` lanza
  `KeyUnavailableError("sin clave")`, `main([])` devuelve 1 y `stderr` contiene `lector-web: sin clave` y
  `Cree la clave con: lector key init`; `block_network` no se llamó.
- `test_main_port_busy`: con `bind_socket` parcheado para lanzar `OSError`, `main(["--port", "8765"])` devuelve 1 y
  `stderr` contiene `lector-web: no se pudo abrir el puerto 8765`.

`tests/unit/web/test_static.py` (cliente autenticado como en la spec 066, con `static_dir` en `tmp_path`):
- `test_serves_built_frontend`: con `tmp_path/dist/index.html` (`<p>hola</p>`) y `tmp_path/dist/assets/a.js`, `GET /`
  devuelve el HTML con las cabeceras de SEG-28 y `GET /assets/a.js` devuelve el archivo; `GET /api/health` sigue
  funcionando.
- `test_without_frontend`: con `static_dir` sin `index.html`, `GET /` da 200 con el texto `Frontend no compilado`.

## Fuera de alcance
- Modo demo (`--demo`, spec 069). Contenido del frontend (specs 070–071). Chequeo con `strace` (spec 072).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `uv run lector-web --help` muestra las opciones `--config`, `--port` y `--no-browser`.
