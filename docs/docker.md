# Usar lectorPlacas con Docker

Con Docker no hace falta instalar uv, Python ni Node: la imagen trae la aplicación, la interfaz web y los modelos.
Los comandos son los mismos en Linux (bash) y en Windows (PowerShell). Todos se ejecutan desde la carpeta del proyecto.

> **Estado de las pruebas:** probado de punta a punta con Docker en Fedora 44, en CPU. Windows (Docker Desktop),
> Podman, Docker sin root y la GPU están **NO VERIFICADOS**. La imagen está diseñada para que funcionen.

## Requisitos

- Docker con Compose v2 (`docker compose version`). En Windows, Docker Desktop.
- Unos 11 GB libres en disco. La imagen ocupa ~10 GB porque incluye las bibliotecas CUDA.
- Conexión a internet solo para construir la imagen, porque los modelos se descargan en ese paso. En ejecución la
  aplicación no usa la red.

## 1. Construir la imagen

```bash
git clone https://github.com/sergiopon/lectorPlacas.git
cd lectorPlacas
docker compose build
```

## 2. Crear la clave maestra (una sola vez)

La base de datos y los recortes se cifran con una clave maestra. La clave se crea dentro del contenedor y queda en el
volumen `lector-keys`:

```bash
docker compose run --rm lector lector key init-file /app/keys/lector_key
```

Si el archivo de clave ya existe, el comando falla en vez de sobrescribirlo.

> **Importante:** sin esta clave no se pueden leer los datos guardados. `docker compose down -v` la borra.

## 3. Poner los videos

Copia los videos a la carpeta `videos/` del proyecto. El contenedor la ve en solo lectura y no puede modificarla.

- Formatos aceptados: `.mp4`, `.mov`, `.mkv`, `.avi`, `.m4v` y `.webm`, de hasta 4 GB.
- Para usar otra carpeta, define `LECTOR_VIDEOS_DIR` antes de arrancar:
  - bash: `export LECTOR_VIDEOS_DIR=/ruta/a/mis/videos`
  - PowerShell: `$env:LECTOR_VIDEOS_DIR="D:\videos"`
- En Linux, los archivos deben ser legibles por otros usuarios (modo 644), porque el contenedor no usa tu usuario.

## 4. Abrir la interfaz web

```bash
docker compose up
```

En la salida aparece una línea `Abra: http://127.0.0.1:8765/auth?token=…`. Ábrela en el navegador.

- El enlace es de un solo uso. Si cierras la sesión, reinicia el contenedor para obtener otro.
- El puerto solo se publica en `127.0.0.1` de tu equipo: nadie más en la red puede entrar.
- Para dejarlo en segundo plano usa `docker compose up -d`, y luego `docker compose logs lector` para ver el enlace.
- **Otro puerto:** por defecto es el 8765. Para usar otro, define `LECTOR_PORT` antes de arrancar; el enlace impreso ya
  sale con ese puerto:
  - bash: `LECTOR_PORT=9000 docker compose up`
  - PowerShell: `$env:LECTOR_PORT="9000"; docker compose up`
- Para detenerlo: `Ctrl+C`, o `docker compose down` si está en segundo plano.

## 5. Usar la línea de comandos

Cada orden se ejecuta en un contenedor temporal que comparte los mismos datos:

```bash
docker compose run --rm lector lector process videos/mi_video.mp4                  # perfil por defecto
docker compose run --rm lector lector process --profile patrulla videos/ruta.mp4   # cámara en vehículo
docker compose run --rm lector lector export --status confirmed                    # CSV en /app/data/exports
docker compose run --rm lector lector purge                                        # borra lo vencido
docker compose run --rm lector lector --help
```

Perfiles disponibles: `parqueadero`, `calle_lenta`, `calle_rapida` y `patrulla`. La referencia completa de órdenes está
en la [guía](guia.md#5-uso-desde-la-terminal-cli). `lector review` abre una ventana de OpenCV y no funciona en Docker;
en su lugar, revisa desde la interfaz web.

## 6. Sacar archivos del contenedor

Los datos viven en volúmenes de Docker, no en carpetas del proyecto. Para copiar las exportaciones a tu equipo, con
el servicio en marcha (`docker compose up -d`):

```bash
docker compose cp lector:/app/data/exports ./exports
```

## 7. Usar la GPU (NVIDIA)

```bash
docker compose --profile gpu up lector-gpu
```

- **Linux:** necesita el controlador NVIDIA y el NVIDIA Container Toolkit.
- **Windows:** necesita Docker Desktop con el motor WSL2 y el controlador NVIDIA de Windows.
- **Podman:** usa CDI (`nvidia.com/gpu=all`) en lugar del bloque `deploy.resources` de `compose.yaml`.

No arranques `lector` y `lector-gpu` a la vez, porque comparten el puerto. Para la línea de comandos con GPU,
cambia `lector` por `lector-gpu` en `docker compose run`.

## Dónde quedan los datos

| Volumen | Ruta en el contenedor | Contenido |
|---|---|---|
| `lector-data` | `/app/data` | Base de datos cifrada, recortes cifrados y exportaciones |
| `lector-logs` | `/app/logs` | Registros, sin textos de placa en claro |
| `lector-keys` | `/app/keys` | Clave maestra (archivo 0400) |

- `docker compose down` conserva los volúmenes.
- `docker compose down -v` **los borra**, junto con la base de datos y la clave.
- Los datos de Docker son independientes de los de una instalación con `uv` en el mismo equipo.

## Actualizar

```bash
git pull
docker compose build
docker compose up
```

Los volúmenes se conservan. Antes de actualizar, haz una copia de la base de datos, con el servicio en marcha:

```bash
docker compose cp lector:/app/data/lector.db ./lector.db.bak
```

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `archivo de clave no encontrado` | Falta el paso 2 (crear la clave). |
| `Permission denied` al leer un video (Linux) | El archivo no es legible por otros: `chmod 644 videos/*`. Con SELinux o Podman, añade `,z` al montaje de videos en `compose.yaml` (`…:/app/videos:ro,z`). |
| `CUDA no disponible en ONNX Runtime` | Se arrancó `lector-gpu` sin GPU accesible. Usa el servicio `lector` (CPU) o instala lo del paso 7. |
| El puerto 8765 está ocupado | Usa otro con `LECTOR_PORT` (paso 4). No edites el puerto en `compose.yaml` a mano: la variable también le dice al servidor qué puerto aceptar. |
| `400` al abrir la página | Entra por `127.0.0.1` o `localhost`, no por otra dirección del equipo. |
