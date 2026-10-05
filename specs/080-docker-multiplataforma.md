# 080 - Docker multiplataforma (Windows, Linux sin root, Podman)

## Objetivo
Que `docker compose` funcione igual en Windows (Docker Desktop, repo en `C:\`, PowerShell), en cualquier distribución
Linux (Docker con o sin root, Podman) y en CPU sin editar YAML. Hoy falla en todos los sistemas: los modelos se
descargan como root con umask 077 y el usuario 1000 del compose no puede leer `/app/models` (comprobado:
`Permission denied`). Además el compose depende de `UID/GID` del anfitrión y de permisos POSIX en bind mounts, que no
existen en NTFS.

Diseño:
- La imagen tiene un usuario fijo sin privilegios `lector` (UID y GID 10001), que descarga los modelos y ejecuta la
  aplicación.
- `data/`, `logs/` y la clave viven en **volúmenes con nombre** de Docker, que heredan el dueño del directorio de la
  imagen. Solo `videos/` es un bind del anfitrión, en solo lectura.
- La variable `LECTOR_EXECUTION_PROVIDER` sustituye a `inference.execution_provider` del YAML.

## Depende de
074, 075, 079.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-02 y ADR-005 (actualización 2026-10-04, spec 080; ya escrita), SEG-04, SEG-11, SEG-20, SEG-28.
- docs/03-modelo-datos.md (variable de entorno nueva; la documenta el orquestador).

## Archivos a crear/modificar
- `Dockerfile`
- `compose.yaml`
- `.gitattributes` (nuevo)
- `src/lector_placas/infrastructure/config.py`
- `tests/unit/test_docker_files.py`
- `tests/unit/infrastructure/test_config_env.py` (nuevo)

## Dependencias externas
Ninguna nueva. Las imágenes base y sus digests no cambian.

## Interfaces y tipos involucrados

### `infrastructure/config.py`
- Constante nueva `EXECUTION_PROVIDER_ENV: Final[str] = "LECTOR_EXECUTION_PROVIDER"`.
- `load_config(path: Path) -> AppConfig` no cambia de firma. Lee el entorno con `os.environ.get(EXECUTION_PROVIDER_ENV)`
  (añadir `import os`).

## Comportamiento esperado

### 1. `load_config`
Después de la línea `data["root_dir"] = path.resolve().parent.parent` y antes de `AppConfig.model_validate(data)`:
1. `value = os.environ.get(EXECUTION_PROVIDER_ENV)`. Si `value` es `None` o `""`, no se hace nada.
2. Si `value` no es `"cpu"` ni `"cuda"`: `raise ConfigurationError("LECTOR_EXECUTION_PROVIDER debe ser 'cpu' o 'cuda'")`.
   El mensaje no incluye el valor recibido.
3. Si `data.get("inference")` es un `dict`, se asigna `data["inference"]["execution_provider"] = value`. Si no es un
   `dict`, no se hace nada: la validación de pydantic informa del error como hoy.
Si con esto `load_config` supera los límites de ruff, extraer los pasos 1–3 a una función privada
`_apply_env_overrides(data: dict[str, object]) -> None` en el mismo módulo.

### 2. `Dockerfile` (la etapa `frontend` no cambia)
Etapa final, en este orden:
1. `FROM`, `COPY --from=ghcr.io/astral-sh/uv…` y el `RUN apt-get …` iguales que hoy.
2. La línea `ENV` actual, con dos cambios: `LECTOR_KEY_FILE=/app/keys/lector_key` (sustituye a
   `/run/secrets/lector_key`) y se añade `LECTOR_EXECUTION_PROVIDER=cpu`. Las demás variables siguen igual.
3. Una línea `RUN groupadd --system --gid 10001 lector && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /app --shell /usr/sbin/nologin lector`.
4. `WORKDIR /app`, los tres `COPY` de proyecto y `RUN uv sync --locked --no-dev`, iguales que hoy (como root).
5. Una línea `RUN mkdir -p models data logs keys videos && chown lector:lector models data logs keys && chmod 0700 models data logs keys`.
6. `USER lector`.
7. `RUN lector models fetch && rm -rf logs/*`. Sustituye a la línea actual, que borraba `logs` entero: `lector` no puede
   borrar el directorio porque `/app` es de root.
8. `COPY --from=frontend /src/frontend/dist frontend/dist`, igual que hoy.
9. Se elimina la línea `RUN mkdir -p data logs videos && chmod 0777 data logs`.
10. `EXPOSE 8765`, `HEALTHCHECK` y `CMD`, iguales que hoy.

### 3. `compose.yaml` (contenido completo, en este orden)
- `services.lector`:
  - `build: .` e `image: lector-placas:local`.
  - Sin clave `user`.
  - `environment` como mapeo con una sola entrada: `LECTOR_EXECUTION_PROVIDER: cpu`.
  - `ports: ["127.0.0.1:8765:8765"]`.
  - `volumes`, en este orden y como cadenas:
    `"${LECTOR_VIDEOS_DIR:-./videos}:/app/videos:ro"`, `"lector-data:/app/data"`, `"lector-logs:/app/logs"`,
    `"lector-keys:/app/keys"`.
  - `restart: "no"`.
- `services.lector-gpu`:
  - `extends: {service: lector}` y `profiles: ["gpu"]`.
  - `environment` como mapeo: `LECTOR_EXECUTION_PROVIDER: cuda`.
  - El bloque `deploy.resources.reservations.devices` actual (driver `nvidia`, `count: all`, `capabilities: [gpu]`).
- `volumes` de nivel superior: `lector-data: {}`, `lector-logs: {}`, `lector-keys: {}`.
- Se eliminan la clave `user`, `secrets` de `services.lector` y el bloque `secrets` de nivel superior.

### 4. `.gitattributes` (nuevo)
Dos líneas exactas:
- `* text=auto eol=lf`
- `*.png binary`

## Casos borde y manejo de errores
- `LECTOR_EXECUTION_PROVIDER` con mayúsculas (`"CPU"`) se rechaza igual que cualquier valor distinto de `cpu`/`cuda`.
- La variable se aplica a todo comando que use `load_config` (`lector` y `lector-web`), dentro y fuera de Docker.

## Tests de aceptación (en prosa)
`tests/unit/infrastructure/test_config_env.py`. Cada test carga el archivo real `config/lector.yaml` del repo, con
`ROOT = Path(__file__).resolve().parents[3]`, y usa `monkeypatch` para el entorno. El YAML trae
`execution_provider: cuda`.
- `test_env_overrides_execution_provider`: con `LECTOR_EXECUTION_PROVIDER=cpu`, `inference.execution_provider == "cpu"`.
  Con `cuda`, da `"cuda"`.
- `test_env_absent_keeps_yaml`: sin la variable (`monkeypatch.delenv(..., raising=False)`), da `"cuda"`.
- `test_env_empty_keeps_yaml`: con la variable vacía `""`, da `"cuda"`.
- `test_env_invalid_rejected`: con `"rocm"` y con `"CPU"`, `ConfigurationError` cuyo mensaje es exactamente
  `LECTOR_EXECUTION_PROVIDER debe ser 'cpu' o 'cuda'`.

`tests/unit/test_docker_files.py`. Los tres tests actuales no cambian; se añaden:
- `test_dockerfile_runs_as_non_root_user`:
  - Existe una línea exactamente igual a `USER lector`, y su índice es menor que el de la línea que contiene
    `lector models fetch`.
  - Ninguna línea contiene `0777` ni `/run/secrets`.
  - La línea que empieza por `ENV` contiene `LECTOR_KEY_FILE=/app/keys/lector_key` y `LECTOR_EXECUTION_PROVIDER=cpu`.
- `test_compose_uses_named_volumes`:
  - Ningún servicio tiene la clave `user` y no existe la clave `secrets` de nivel superior.
  - Las claves de `volumes` de nivel superior son exactamente `{"lector-data", "lector-logs", "lector-keys"}`.
  - `services.lector.volumes` es exactamente la lista de cuatro cadenas del §3, en ese orden.
- `test_compose_execution_provider`: `services.lector.environment == {"LECTOR_EXECUTION_PROVIDER": "cpu"}` y
  `services["lector-gpu"].environment == {"LECTOR_EXECUTION_PROVIDER": "cuda"}`.
- `test_gitattributes_forces_lf`: las líneas de `.gitattributes` son exactamente `["* text=auto eol=lf", "*.png binary"]`.

## Fuera de alcance
- La documentación de uso (`docs/guia.md`), los ADR y las reglas: los actualiza el orquestador.
- Verificar la GPU en Docker (sigue **NO VERIFICADO**). Cambiar imágenes base o digests.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde, sin modificar tests existentes.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `docker compose config` no da error.
- [ ] La construcción y la prueba de punta a punta de la imagen las hace el orquestador.
