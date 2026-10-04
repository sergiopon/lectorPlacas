# 075 - Imagen Docker y `compose.yaml` (puerto solo en el loopback del anfitrión)

## Objetivo
Ejecutar lectorPlacas con `docker compose up` sin instalar uv, Python ni Node en el equipo: una imagen multietapa que
compila el frontend, instala el proyecto con `uv sync --locked`, descarga y verifica los modelos al construir y arranca
`lector-web`. La clave maestra llega por un Docker secret (`LECTOR_KEY_FILE`, spec 074). El puerto se publica **solo**
en `127.0.0.1` del anfitrión; dentro del contenedor el servidor escucha en `0.0.0.0` únicamente con
`LECTOR_IN_CONTAINER=1` (excepción acotada de SEG-28).

## Depende de
068, 070, 074.

## Archivos rectores aplicables
- docs/08 §4.8; ADR-016; reglas-seguridad.md SEG-02, SEG-11, SEG-20, SEG-28 (excepción de contenedor ya escrita).

## Archivos a crear/modificar
- `Dockerfile` (nuevo), `compose.yaml` (nuevo), `.dockerignore` (nuevo)
- `.gitignore` (añadir `secrets/`)
- `src/lector_placas/web/app.py` (`bind_host`)
- `tests/unit/web/test_app.py` (un test nuevo)
- `tests/unit/test_docker_files.py` (nuevo)

## Dependencias externas (verificadas el 2026-10-04 con `docker buildx imagetools inspect` y ejecutando la imagen)
- `node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c` (Node 22.23.3).
- `python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f` (Python 3.13.16, Debian
  13 trixie).
- `ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424` (misma versión
  de uv que el desarrollo).
- En esa imagen de Python, `import cv2` (opencv-python 4.14.0.94) falla con `libxcb.so.1: cannot open shared object
  file` y funciona tras `apt-get install --no-install-recommends libgl1 libglib2.0-0t64`; `sqlcipher3` 0.6.2 trae su
  propia SQLCipher en la wheel manylinux (comprobado: SQLite 3.51.1).
- **NO VERIFICADO**: el perfil `gpu` (en este equipo no está el NVIDIA Container Toolkit). Se escribe, pero el Definition
  of Done solo prueba la CPU.

## Interfaces y tipos involucrados

### `web/app.py`
- `CONTAINER_ENV: Final[str] = "LECTOR_IN_CONTAINER"`; `CONTAINER_BIND: Final[str] = "0.0.0.0"`.
- `def bind_host() -> str`: `CONTAINER_BIND` si `os.environ.get(CONTAINER_ENV) == "1"`; si no, `HOST`.
- `bind_socket` hace `bind((bind_host(), port))` y `uvicorn.Config(..., host=bind_host(), ...)`. `launch_url` y los
  mensajes de la salida estándar siguen usando `HOST` (`127.0.0.1`), que es la dirección del anfitrión.

## Comportamiento esperado

### 1. `Dockerfile` (en este orden)
1. Etapa `frontend`: `FROM <node con digest> AS frontend`; `WORKDIR /src/frontend`; `COPY frontend/package.json
   frontend/package-lock.json ./`; `RUN npm ci`; `COPY frontend/ ./`; `RUN npm run build`.
2. Etapa final: `FROM <python con digest>`; `COPY --from=<uv con digest> /uv /uvx /bin/`;
   `RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 && rm -rf /var/lib/apt/lists/*`.
3. `ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never LECTOR_IN_CONTAINER=1
   LECTOR_KEY_FILE=/run/secrets/lector_key PATH=/app/.venv/bin:$PATH`; `WORKDIR /app`.
4. `COPY pyproject.toml uv.lock README.md LICENSE ./`, `COPY src/ src/`, `COPY config/ config/`;
   `RUN uv sync --locked --no-dev`.
5. `RUN lector models fetch && rm -rf logs` (única etapa con red; los modelos quedan verificados por SHA-256 dentro de
   la imagen; el log de la descarga no se guarda).
6. `COPY --from=frontend /src/frontend/dist frontend/dist`.
7. `RUN mkdir -p data logs videos && chmod 0777 data logs` (los volúmenes los sustituyen; así también funciona sin
   volúmenes con cualquier `user`).
8. `EXPOSE 8765`; `HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8765/', headers={'Host': '127.0.0.1:8765'}), timeout=3)"`.
9. `CMD ["lector-web", "--no-browser", "--port", "8765"]`.

### 2. `compose.yaml`
- Servicio `lector`: `build: .`, `image: lector-placas:local`, `user: "${UID:-1000}:${GID:-1000}"`,
  `ports: ["127.0.0.1:8765:8765"]`, `volumes: ["./videos:/app/videos:ro", "./data:/app/data", "./logs:/app/logs"]`,
  `secrets: [lector_key]`, `restart: "no"`.
- Servicio `lector-gpu`: igual que `lector` (con `extends` sobre `lector` o repetido), `profiles: ["gpu"]` y
  `deploy.resources.reservations.devices: [{driver: nvidia, count: all, capabilities: [gpu]}]`. Solo se ejecuta uno a la
  vez (mismo puerto).
- `secrets: {lector_key: {file: ./secrets/lector_key}}`.

### 3. `.dockerignore`
Exactamente estas líneas (una por línea): `.git`, `.venv`, `data`, `videos`, `models`, `logs`, `secrets`, `training`,
`tests`, `frontend/node_modules`, `frontend/dist`, `frontend/test-results`, `frontend/playwright-report`,
`frontend/e2e/.auth`, `CLAUDE.md`, `CONTEXT.md`, `docs/05-orquestacion.md`, `**/__pycache__`.

### 4. Uso (lo documenta el orquestador en el README)
```
mkdir -m 700 -p secrets videos data logs
docker compose build
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/secrets:/secrets" lector-placas:local lector key init-file /secrets/lector_key
UID=$(id -u) GID=$(id -g) docker compose up
```
La URL con el token aparece en la salida de `docker compose up` (`Abra: http://127.0.0.1:8765/auth?token=…`); el token
es de un solo uso.

## Casos borde y manejo de errores
- Sin `secrets/lector_key`, `docker compose up` falla al montar el secret (mensaje de Docker). Con un archivo de otro
  usuario o con permisos abiertos, `lector-web` termina con el mensaje de la spec 074.
- Sin GPU en el contenedor, ONNX Runtime cae a CPU con su aviso (como fuera de Docker).

## Tests de aceptación (en prosa)
`tests/unit/web/test_app.py` (añadir):
- `test_bind_host_container`: con `LECTOR_IN_CONTAINER=1`, `bind_host()` es `"0.0.0.0"`; sin la variable o con
  `"true"`, es `"127.0.0.1"`.

`tests/unit/test_docker_files.py` (lee los archivos de la raíz del repo):
- `test_dockerfile_pins_digests`: cada línea que empieza por `FROM` y el `COPY --from=` de uv contienen `@sha256:`.
- `test_compose_publishes_loopback_only`: cada elemento de `ports` de cada servicio de `compose.yaml` (cargado con
  `yaml.safe_load`) empieza por `127.0.0.1:`.
- `test_dockerignore_excludes_private_data`: `.dockerignore` contiene `data`, `videos`, `models`, `secrets`,
  `CLAUDE.md`, `CONTEXT.md` y `docs/05-orquestacion.md`.

## Fuera de alcance
- Publicar la imagen en un registro. Probar el perfil `gpu`.

## Definition of Done
- [ ] `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy src` limpios.
- [ ] `docker compose build` sin errores; pegar el tamaño de la imagen (`docker image ls lector-placas:local`).
- [ ] Con `secrets/lector_key` creado por el comando del §4, `UID=$(id -u) GID=$(id -g) docker compose up -d`, el
      contenedor llega a `healthy` (`docker compose ps`), `curl -s -o /dev/null -w "%{http_code}" -c jar "<URL de Abra:>"`
      da `303`, `curl -s -b jar -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/api/health` da `200`, y
      `ss -Hltn | grep 8765` solo muestra `127.0.0.1:8765`. Después `docker compose down` y borrar `secrets/lector_key`.
