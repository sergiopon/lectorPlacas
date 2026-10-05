# 082 - `lector review` en Docker con la pantalla X11 del anfitrión

## Objetivo
Que `lector review` (ventana de OpenCV) funcione desde Docker en Linux, usando la pantalla X11 o Xwayland del
anfitrión, sin abrir esa pantalla a otros usuarios ni a la red. Se añaden:
- un servicio `lector-review` en `compose.yaml`, sin puertos y sin red;
- un script `scripts/review-docker.sh`, que da acceso temporal al socket X y a una copia de la cookie solo al usuario
  del contenedor (UID 10001) y lo retira al terminar.

**Prototipo hecho por el orquestador el 2026-10-04** (Fedora 44, GNOME en Wayland con Xwayland, `DISPLAY=:0`; imagen de
la spec 081):
- Al plugin `xcb` de Qt (wheel `opencv-python` 4.14.0.94) le faltan `libICE.so.6` y `libSM.so.6`. Con el paquete
  Debian `libsm6`, que trae `libice6`, `cv2.imshow` abre la ventana como UID 10001.
- El socket `/tmp/.X11-unix/X0` es `srwxr-xr-x` del usuario del anfitrión. Sin una ACL `u:10001:rw` la conexión falla;
  con ella funciona.
- La cookie de Xwayland (0600) se copia con la familia comodín y se le da `u:10001:r`.
- Funciona con `--network none`: la conexión X va por el socket Unix montado.

## Depende de
080, 081.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-20 y SEG-28, y ADR-016 (el orquestador añade la nota de esta spec antes de lanzarla).

## Archivos a crear/modificar
- `Dockerfile`
- `compose.yaml`
- `scripts/review-docker.sh` (nuevo, ejecutable: modo 0755 en git)
- `tests/unit/test_docker_files.py`

## Dependencias externas
- Paquete Debian `libsm6` (trixie), instalado con `apt-get` en la imagen.
- En el anfitrión: `xauth` y `setfacl` (paquete `acl`), que el script comprueba.

## Comportamiento esperado

### 1. `Dockerfile`
En la línea `RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 && …`, añadir
`libsm6` justo después de `libglib2.0-0t64`. Nada más cambia.

### 2. `compose.yaml`
Añadir un tercer servicio `lector-review`, después de `lector-gpu`, **sin `extends`**, con estas claves en este orden:
- `image: lector-placas:local`. Sin `build`: reutiliza la imagen que construye `lector`.
- `profiles: ["review"]`.
- `network_mode: none`.
- `environment` como mapeo, en este orden:
  - `LECTOR_EXECUTION_PROVIDER: cpu`
  - `DISPLAY: "${DISPLAY:-:0}"`
  - `XAUTHORITY: /tmp/lector-review.xauth`
  - `QT_X11_NO_MITSHM: "1"`
- `volumes` como cadenas, en este orden:
  1. `"${LECTOR_VIDEOS_DIR:-./videos}:/app/videos:ro"`
  2. `"lector-data:/app/data"`
  3. `"lector-logs:/app/logs"`
  4. `"lector-keys:/app/keys"`
  5. `"${LECTOR_X11_DIR:-/tmp/.X11-unix}:/tmp/.X11-unix:ro"`
  6. `"${LECTOR_XAUTH:-/dev/null}:/tmp/lector-review.xauth:ro"`
- `command: ["lector", "review"]`.
- `restart: "no"`.

Sin `ports`.

### 3. `scripts/review-docker.sh`
Script de bash. Primera línea `#!/usr/bin/env bash` y segunda `set -euo pipefail`. Pasos en orden:
1. **Constantes:** `CONTAINER_UID=10001`; `XAUTH_COPY="${XDG_RUNTIME_DIR:-/tmp}/lector-review.xauth"`.
2. **Comprobaciones previas.** Cada error escribe su mensaje en stderr y sale con código 1:
   - si `DISPLAY` está vacía o no definida: `review-docker: no hay pantalla X (DISPLAY vacía)`;
   - si `DISPLAY` no empieza por `:` (pantalla remota o por red): `review-docker: solo se admiten pantallas locales (DISPLAY=:N)`;
   - si falta el comando `xauth` o `setfacl` (`command -v`): `review-docker: falta <comando>; instale xauth y acl`.
3. **Número de pantalla y socket:** `DISPLAY_NUM` es lo que va tras `:` hasta el primer `.`, si lo hay (`:0.0` → `0`).
   `SOCKET="/tmp/.X11-unix/X${DISPLAY_NUM}"`. Si no es un socket (`[ -S "$SOCKET" ]` falso):
   `review-docker: no existe el socket $SOCKET` y sale con 1.
4. **Limpieza garantizada:** función `cleanup` que ejecuta `setfacl -x "u:${CONTAINER_UID}" "$SOCKET"` y
   `rm -f "$XAUTH_COPY"`, ambos con `|| true`. Registrarla con `trap cleanup EXIT` **antes** del paso 5.
5. **Cookie:**
   1. `rm -f "$XAUTH_COPY"`.
   2. `(umask 077 && : > "$XAUTH_COPY")`, que crea el archivo vacío en 0600.
   3. `xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f "$XAUTH_COPY" nmerge -`.
   4. `setfacl -m "u:${CONTAINER_UID}:r" "$XAUTH_COPY"`.
6. **Socket:** `setfacl -m "u:${CONTAINER_UID}:rw" "$SOCKET"`.
7. **Ejecución:** `cd` a la raíz del repo (el directorio padre de la carpeta del script, con
   `"$(dirname "$0")/.."`). Luego, sin `exec` para que el `trap` se ejecute:
   `LECTOR_XAUTH="$XAUTH_COPY" docker compose --profile review run --rm lector-review lector review "$@"`.
   El código de salida del script es el de ese comando: guardarlo con `status=$?` usando `set +e` justo antes y
   `set -e` después, y terminar con `exit "$status"`.

El script no usa `xhost` en ningún caso.

## Casos borde y manejo de errores
- `DISPLAY=:1` → socket `/tmp/.X11-unix/X1`. `DISPLAY=:0.0` → `X0`.
- `DISPLAY=localhost:10.0` → mensaje de "solo se admiten pantallas locales" y código 1, sin tocar ACL.
- Si `docker compose` falla, el `trap` igual retira la ACL y borra la copia.

## Tests de aceptación (en prosa)
`tests/unit/test_docker_files.py` (añadir; los existentes no cambian):
- `test_dockerfile_installs_libsm6`: la línea del `Dockerfile` que contiene `apt-get install` contiene `libsm6`.
- `test_compose_review_service`. Con `services["lector-review"]`:
  - no tiene `ports` ni `extends`;
  - `profiles == ["review"]` y `network_mode == "none"`;
  - `command == ["lector", "review"]`;
  - sus 4 primeros `volumes` son iguales a `services.lector.volumes`;
  - `environment["XAUTHORITY"] == "/tmp/lector-review.xauth"`.
- `test_review_script_is_safe`. Con `scripts/review-docker.sh`:
  - existe y es ejecutable (`os.access(path, os.X_OK)`);
  - contiene `trap cleanup EXIT`, `setfacl -x` y `--profile review run --rm lector-review lector review`;
  - no contiene `xhost`.

## Fuera de alcance
- Cambiar `opencv_review_ui.py` o cualquier archivo de `src/`.
- Windows (WSLg) y macOS: los documenta el orquestador como NO VERIFICADOS.
- La documentación de uso (la escribe el orquestador).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `bash -n scripts/review-docker.sh` sin errores.
- [ ] `docker compose --profile review config` sin errores.
- [ ] Construir la imagen y la prueba de punta a punta con la ventana las hace el orquestador.
