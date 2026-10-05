# 081 - Puerto configurable en Docker

## Objetivo
Que quien use la imagen pueda publicar la web en el puerto del anfitrión que quiera (`LECTOR_PORT`), no solo en 8765.
Hoy no se puede: el servidor solo acepta peticiones cuya cabecera `Host` lleve el puerto en el que escucha **dentro**
del contenedor (8765). Si el anfitrión publica otro puerto (9000), el navegador envía `Host: 127.0.0.1:9000` y recibe
400. Además el enlace impreso apunta a 8765.

Diseño:
- Dentro del contenedor la app sigue escuchando en 8765.
- La variable `LECTOR_PUBLIC_PORT` (solo con `LECTOR_IN_CONTAINER=1`) dice qué puerto ve el navegador. Se usa para la
  cabecera `Host` permitida y para el enlace impreso.
- En el anfitrión, el puerto sigue publicado solo en `127.0.0.1`.

También se corrige la pista que se imprime cuando falta la clave. Con `LECTOR_KEY_FILE` definida, que es el caso de
Docker, la pista debe indicar `key init-file`, no `key init`.

## Depende de
075, 080.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-28 (actualizada por el orquestador antes de lanzar esta spec), ADR-016.

## Archivos a crear/modificar
- `src/lector_placas/web/app.py`
- `Dockerfile`
- `compose.yaml`
- `tests/unit/web/test_app.py`
- `tests/unit/test_docker_files.py`

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `web/app.py`
- Constantes nuevas:
  - `PUBLIC_PORT_ENV: Final[str] = "LECTOR_PUBLIC_PORT"`
  - `KEY_FILE_HINT: Final[str] = "Cree la clave con: lector key init-file {path}"`
  - `KEY_HINT` no cambia.
- Función nueva `def public_port(listen_port: int) -> int`.
- Función nueva `def key_hint() -> str`.
- Importar `ConfigurationError` de `lector_placas.domain.errors` y `KEY_FILE_ENV` de
  `lector_placas.adapters.security.file_key_provider` (cli ya importa adaptadores; web puede importar adaptadores).

## Comportamiento esperado

### `public_port(listen_port)`
1. Si `os.environ.get(CONTAINER_ENV) != "1"`, devuelve `listen_port`. Fuera de Docker la variable se ignora.
2. `value = os.environ.get(PUBLIC_PORT_ENV)`. Si es `None` o `""`, devuelve `listen_port`.
3. Si `value.isdecimal()` es falso, o `int(value)` no está en `[1, MAX_PORT]`:
   `raise ConfigurationError("LECTOR_PUBLIC_PORT debe ser un entero entre 1 y 65535")`.
4. Devuelve `int(value)`.

### `key_hint()`
- Si `os.environ.get(KEY_FILE_ENV)` no está vacía, devuelve `KEY_FILE_HINT.format(path=<ese valor>)`.
- Si no, devuelve `KEY_HINT`.

### `main`
- Dentro del primer bloque `try` (el que captura `LectorPlacasError`), justo después de `load_config`, llamar a
  `public_port(args.port)` y descartar el resultado. Solo valida: un valor inválido sale por la rama existente con
  `lector-web: LECTOR_PUBLIC_PORT debe ser un entero entre 1 y 65535` y código 1.
- En esa misma rama, `sys.stderr.write(f"{KEY_HINT}\n")` pasa a `sys.stderr.write(f"{key_hint()}\n")`.

### `_serve`
Después de `port = sock.getsockname()[1]`, añadir `shown_port = public_port(port)`, y usar `shown_port` en lugar de
`port` en tres sitios: `allowed_hosts_for(...)`, `launch_url(...)` y el mensaje `lectorPlacas web en http://…`.
`uvicorn.Config(port=port)` sigue con `port`, el puerto real de escucha.

### `Dockerfile`
- En la línea `ENV`, añadir `LECTOR_PUBLIC_PORT=8765` después de `LECTOR_EXECUTION_PROVIDER=cpu`.
- La línea `HEALTHCHECK` pasa a leer el puerto público para la cabecera `Host`. El `CMD` de Python, dentro de las
  mismas comillas dobles, queda con exactamente este texto:
  `import os, urllib.request as u; p = os.environ.get('LECTOR_PUBLIC_PORT') or '8765'; u.urlopen(u.Request('http://127.0.0.1:8765/', headers={'Host': '127.0.0.1:' + p}), timeout=3)`.
  Las opciones `--interval=30s --timeout=5s --start-period=60s` no cambian.

### `compose.yaml`
- `services.lector.ports` pasa a `["127.0.0.1:${LECTOR_PORT:-8765}:8765"]`.
- `services.lector.environment` pasa a tener dos entradas, en este orden:
  - `LECTOR_EXECUTION_PROVIDER: cpu`
  - `LECTOR_PUBLIC_PORT: "${LECTOR_PORT:-8765}"`
- `services.lector-gpu.environment` no cambia (`LECTOR_EXECUTION_PROVIDER: cuda`). Hereda `LECTOR_PUBLIC_PORT` y los
  puertos por `extends`.

## Casos borde y manejo de errores
- `LECTOR_PUBLIC_PORT="0"`, `"65536"`, `"9000a"` o `" 9000"` → `ConfigurationError` con el mensaje del paso 3.
- `LECTOR_PUBLIC_PORT` sin `LECTOR_IN_CONTAINER=1` → se ignora, aunque sea inválida.

## Tests de aceptación (en prosa)
`tests/unit/web/test_app.py` (añadir; los existentes no cambian):
- `test_public_port_outside_container`: sin `LECTOR_IN_CONTAINER` y con `LECTOR_PUBLIC_PORT=9000`,
  `public_port(8765) == 8765`.
- `test_public_port_in_container`: con `LECTOR_IN_CONTAINER=1`:
  - con `LECTOR_PUBLIC_PORT=9000`, `public_port(8765) == 9000`;
  - con la variable vacía, `8765`;
  - sin la variable, `8765`.
- `test_public_port_invalid`: con `LECTOR_IN_CONTAINER=1` y cada valor `"0"`, `"65536"`, `"9000a"` y `" 9000"`,
  `ConfigurationError` con mensaje exacto `LECTOR_PUBLIC_PORT debe ser un entero entre 1 y 65535`.
- `test_key_hint`:
  - con `LECTOR_KEY_FILE=/app/keys/lector_key`, devuelve `Cree la clave con: lector key init-file /app/keys/lector_key`;
  - sin la variable, `Cree la clave con: lector key init`.
- `test_serve_uses_public_port`: con `LECTOR_IN_CONTAINER=1` y `LECTOR_PUBLIC_PORT=9000`, sustituir `create_app` y
  `uvicorn.Server` del módulo por dobles con `monkeypatch`. Se llama a `_serve` con un socket real ligado a
  `("127.0.0.1", 0)`. Se comprueba:
  - el `allowed_hosts` que recibe `create_app` es `frozenset({"127.0.0.1:9000", "localhost:9000"})`;
  - la salida estándar contiene `http://127.0.0.1:9000/auth?token=`.

  Los dobles son mínimos y se definen dentro del test.

`tests/unit/test_docker_files.py`: en `test_compose_execution_provider` cambia solo la expectativa de `lector`, que
pasa a `{"LECTOR_EXECUTION_PROVIDER": "cpu", "LECTOR_PUBLIC_PORT": "${LECTOR_PORT:-8765}"}`. Se añade:
- `test_compose_port_is_configurable`: `services.lector.ports == ["127.0.0.1:${LECTOR_PORT:-8765}:8765"]`. La línea
  `ENV` del `Dockerfile` contiene `LECTOR_PUBLIC_PORT=8765`, y la línea `HEALTHCHECK` contiene `LECTOR_PUBLIC_PORT`.

## Fuera de alcance
- Cambiar el puerto interno 8765, la lógica de `allowed_hosts_for` o el comportamiento fuera de Docker.
- La documentación de uso (la actualiza el orquestador).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde. Solo cambia `test_compose_execution_provider`, como se indica.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `docker compose config` sin error, y `LECTOR_PORT=9000 docker compose config` muestra `published: "9000"`.
