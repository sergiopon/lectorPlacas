# Reglas de seguridad — lectorPlacas

> Archivo rector. Toda spec y toda implementación DEBEN cumplirlo. Cada regla es verificable.
> Marco: Ley 1581 de 2012 (Colombia): las placas son dato personal. Requisitos: RF-25..RF-33,
> RNF-07..RNF-12, RNF-15 de `docs/00-requisitos.md`.

## 1. Datos personales (Ley 1581 de 2012)

| ID | Regla |
|---|---|
| SEG-01 | La BD DEBE estar cifrada con SQLCipher; los recortes DEBEN estar cifrados con AES-256-GCM (ADR-005). NO DEBE existir ningún archivo con texto de placa o imagen de placa en claro en disco. |
| SEG-02 | La clave maestra DEBE vivir solo en el keyring del SO (servicio `lector-placas`, usuario `master-key`). NO DEBE escribirse en disco, logs, variables de entorno, config ni repo. Excepción (spec 074, ADR-005 actualización 2026-10-03): para contenedores, `lector key export-file`/`init-file` la escriben en un archivo creado con `O_EXCL` y modo 0400, y `FileKeyProvider` solo la lee si `LECTOR_KEY_FILE` es una ruta absoluta a un archivo regular del mismo usuario sin permisos de grupo ni otros. Ese archivo NO DEBE estar dentro del repo, de la imagen ni de `data/`; la variable de entorno lleva la ruta, nunca la clave. En Docker vive en el volumen con nombre `lector-keys` (`/app/keys/lector_key`, spec 080). |
| SEG-03 | Retención: recortes DEBEN borrarse a los 30 días (excepción temporal vigente: 90 días, decidida por el usuario el 2026-09-27 para construir el filtro de legibilidad, docs/historial/08 §2.2; se vuelve a 30 cuando exista el dataset de la spec 055) y registros (avistamientos, corridas, placas huérfanas, exportaciones) a los 90 días (`retention` en config). La purga DEBE ejecutarse al inicio de todo comando que abra la BD, al abrir la sesión de la GUI (`lector-gui`) y con `lector purge` o la acción de purga de la GUI. Las exportaciones de entrenamiento (`training/ocr/datasets/own/` y `training/legibility/datasets/own/`) se borran a los `retention.training_days` días (180 por defecto) con la misma purga. |
| SEG-04 | Todo el proceso DEBE ejecutarse con `os.umask(0o077)` (primera instrucción de `cli/main.py` y de `web/app.py:main`). Directorios de datos, logs y exportaciones DEBEN ser 0700; archivos 0600. |
| SEG-05 | Los logs NO DEBEN contener texto de placa en claro: el código DEBE usar `mask_plate()` y los handlers DEBEN tener `PlateRedactionFilter`. `audit_log.detail` NO DEBE contener texto de placa. |
| SEG-06 | NO DEBE guardarse la ruta ni el nombre del video en BD; solo su SHA-256 y metadatos técnicos. |
| SEG-07 | Los recortes descifrados NO DEBEN escribirse a disco; solo existen en memoria durante la revisión. Excepción controlada (decisión del usuario 2026-09-26): `lector dataset export-reviewed` escribe los recortes de avistamientos `confirmed`/`corrected` en `training/ocr/datasets/own/` (directorios 0700, archivos 0600, gitignored), registra `audit_log` y solo sirve para reentrenar el OCR localmente; nunca salen de la máquina ni van a la API externa. La misma excepción cubre `lector dataset export-legibility` (spec 055, decisión del usuario 2026-09-27, docs/historial/08 §2): recortes de avistamientos `confirmed`/`corrected`/`illegible`/`rejected` en `training/legibility/datasets/own/`, **sin texto de placa ni hash de video** en el CSV, para entrenar el filtro de legibilidad. |
| SEG-08 | La exportación CSV DEBE escribirse solo en `data/exports/` (0600), registrarse en `audit_log` y protegerse contra inyección CSV (prefijo `'`). |

## 2. API externa (DeepSeek) y datos de prueba

| ID | Regla |
|---|---|
| SEG-09 | A la API externa SOLO se envían specs, `CONTEXT.md` y código. NO DEBEN enviarse videos, frames, recortes, placas reales, la BD, logs, exportaciones, ground truth ni la clave. |
| SEG-10 | Todo fixture y ejemplo DEBE ser sintético: imágenes generadas con numpy/OpenCV, videos generados con PyAV en el test, placas inventadas que sigan el formato (p. ej. `ABC123`, `XYZ98K`). NO DEBEN versionarse imágenes o videos reales. |
| SEG-11 | `data/`, `models/`, `logs/`, `videos/`, `training/**/datasets/`, `training/**/runs/`, `*.db`, `*.csv` fuera de `tests/`, `.env` DEBEN estar en `.gitignore`. |

## 3. Entradas y rutas

| ID | Regla |
|---|---|
| SEG-12 | El video de entrada DEBE: tener extensión en `input.allowed_extensions` (comparada en minúsculas), ser archivo regular (no symlink, no dispositivo), pesar ≤ `max_file_size_mb`, estar dentro de un `input.allowed_dirs` tras `Path.resolve(strict=True)`, y abrir con PyAV con al menos un stream de video. |
| SEG-13 | Toda ruta de salida (BD, recortes, exportaciones, logs, modelos) DEBE resolverse con `resolve_within(base, candidate)`; si escapa de su base → `UnsafePathError`. Los nombres de archivo generados NO DEBEN derivar de datos de entrada (solo ids aleatorios o timestamps). |
| SEG-14 | Los archivos YAML DEBEN leerse con `yaml.safe_load`. NO DEBE usarse `yaml.load`, `pickle`, `eval`, `exec` ni `shell=True`. |

## 4. Base de datos

| ID | Regla |
|---|---|
| SEG-15 | Todas las consultas DEBEN ser parametrizadas (`?`). NO DEBE construirse SQL con f-strings, `%` o concatenación. Única excepción: `PRAGMA key = "x'<hex>'"` con el hex validado por `^[0-9a-f]{64}$` inmediatamente antes. |
| SEG-16 | Una clave incorrecta DEBE producir `EncryptionError` sin revelar la clave ni el contenido. |

## 5. Modelos

| ID | Regla |
|---|---|
| SEG-17 | Los modelos DEBEN cargarse solo desde `models/<model_id>/<filename>` tras verificar su SHA-256 contra `config/models.yaml` en cada carga. Discrepancia → `ModelIntegrityError`, el proceso termina. |
| SEG-18 | El código de `src/` NO DEBE llamar `torch.load` ni importar `torch`/`ultralytics`. En `training/`, cualquier `torch.load` propio DEBE usar `weights_only=True`. Excepción documentada: Ultralytics carga internamente `yolo26n.pt` (pickle); solo se permite tras verificar su SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`, y los checkpoints (`best.pt`/`last.pt`) producidos localmente por el propio entrenamiento en `training/detector/runs/`. NO DEBEN cargarse `.pt` de otras fuentes. |
| SEG-19 | Los adaptadores DEBEN pasar rutas locales a las librerías (`onnx_model_path`, `plate_config_path`, `model_path`). NO DEBEN usar nombres de hub que disparen descargas. |

## 6. Red

| ID | Regla |
|---|---|
| SEG-20 | En runtime NO DEBE haber llamadas de red. Todo comando excepto `lector models fetch` DEBE llamar `block_network()` antes de cargar modelos o abrir la BD; `lector-web` DEBE llamarla antes de abrir su socket (SEG-28). La clave maestra se lee del keyring antes de `block_network()`: el keyring usa D-Bus sobre un socket Unix local, que la guardia también bloquea. Excepción: `lector dataset download` y `lector dataset prepare` (spec 036) también usan red, solo para descargar datasets de entrenamiento. `block_network()` es una guardia de Python y no frena código nativo: ONNX Runtime 1.30 trae telemetría de Microsoft (subida HTTPS desde un hilo C++, verificada con `strace`), por lo que el paquete `lector_placas` DEBE fijar `ORT_DISABLE_TELEMETRY=1` en `lector_placas/__init__.py`, antes de que se importe `onnxruntime`. Fijarla después del import o llamar a `onnxruntime.disable_telemetry_events()` NO basta (verificado). El nivel F (`strace -f -e trace=connect`) es la comprobación de esta regla. |
| SEG-21 | `lector models fetch` DEBE aceptar solo URLs `https://github.com/` del manifiesto y verificar tamaño y SHA-256 antes de mover el archivo a `models/`. `lector dataset download` solo llama a `https://api.roboflow.com` y al enlace `https` de exportación que esa API devuelve; la API key se lee solo de la variable de entorno `ROBOFLOW_API_KEY` y NO DEBE aparecer en logs, mensajes de error, archivos ni el repo. |
| SEG-22 | En `training/`, los scripts DEBEN exportar `YOLO_OFFLINE=True` y `YOLO_AUTOINSTALL=False`, salvo el paso explícito de descarga de pesos base. |

## 6b. Interfaz gráfica (ADR-016)

| ID | Regla |
|---|---|
| SEG-27 | **Retirada** (2026-10-04, spec 073): regía la GUI PySide6, que ya no existe. Sus garantías para la interfaz las cubre SEG-28. |
| SEG-28 | Interfaz web (ADR-016). El servidor DEBE escuchar solo en `127.0.0.1` (única excepción: dentro de un contenedor con `LECTOR_IN_CONTAINER=1`, spec 075, publicando el puerto solo en el loopback del anfitrión). DEBE rechazar con 400 toda petición cuya cabecera `Host` no sea `127.0.0.1:<puerto>` ni `localhost:<puerto>`; `<puerto>` es el de escucha o, solo dentro de un contenedor, el publicado en el anfitrión (`LECTOR_PUBLIC_PORT`, spec 081). El token de arranque es de un solo uso y se canjea por una cookie de sesión aleatoria `HttpOnly`, `SameSite=Strict`, `Path=/`; toda ruta `/api/*` sin cookie válida responde 401. Todas las respuestas DEBEN llevar `Content-Security-Policy` sin orígenes externos, `Referrer-Policy: no-referrer` y `X-Content-Type-Options: nosniff`; las de `/api/*` y los recortes, `Cache-Control: no-store`. Los recortes se descifran en memoria y nunca tocan el disco (SEG-07). El video original (`/api/runs/{id}/video`) y el fotograma completo (`/api/sightings/{id}/frame`, spec 076) se sirven solo con sesión válida: el video se localiza por SHA-256 entre los archivos de `allowed_dirs` (caché solo en memoria; la BD sigue sin ruta ni nombre, SEG-06), sin `Content-Disposition`, y el fotograma se decodifica en memoria y nunca se escribe a disco. El log de acceso de Uvicorn DEBE estar desactivado y ningún log, mensaje de error ni ruta lleva texto de placa (la búsqueda por placa va en query, nunca en la ruta, y no se registra). El frontend NO DEBE cargar scripts, estilos ni fuentes de CDN ni enviar telemetría. NO DEBE relajarse `block_network()`. |
| SEG-29 | El sistema NO DEBE leer, derivar ni guardar ubicación (GPS, metadatos de ubicación del contenedor de video, nombres de calle) ni la hora absoluta de grabación de un avistamiento. Solo DEBE guardarse el recorte de la placa: nunca el del vehículo ni el frame completo. NO DEBE implementarse cotejo con listas de placas buscadas, alertas ni consulta a bases externas sin un ADR propio y la validación legal del uso previsto. La retención (SEG-03) es la misma en los dos modos de cámara (ADR-017). |

## 7. Dependencias y secretos

| ID | Regla |
|---|---|
| SEG-23 | Todas las dependencias DEBEN fijarse con `==` en `pyproject.toml` y resolverse en `uv.lock` versionado. Instalación con `uv sync --locked`. |
| SEG-24 | `uv run pip-audit` DEBE ejecutarse en pre-commit y no reportar vulnerabilidades sin justificar (las excepciones se documentan en `docs/adr/`). |
| SEG-25 | NO DEBE haber secretos en el código ni en el repo (incluida la API key de DeepSeek). Los secretos del desarrollador viven en `.env` (en `.gitignore`) o en el keyring. |
| SEG-26 | Mensajes de error NO DEBEN incluir claves, texto de placa en claro ni contenido de archivos. |

## 8. Checklist de revisión de seguridad (aplicar a cada implementación)

- [ ] ¿Hay algún `print`, log o mensaje de error con texto de placa sin `mask_plate`? (SEG-05, SEG-26)
- [ ] ¿Algún SQL no parametrizado? `grep -nE "execute\(f|execute\(.*%|execute\(.*\+" src/` vacío (SEG-15)
- [ ] ¿Se usa `yaml.load`, `pickle`, `eval`, `exec`, `shell=True`, `torch.load`? (SEG-14, SEG-18)
- [ ] ¿Toda ruta de salida pasa por `resolve_within` y todo directorio por `ensure_private_dir`? (SEG-04, SEG-13)
- [ ] ¿Los archivos nuevos se crean 0600 y de forma atómica cuando contienen datos? (SEG-04)
- [ ] ¿Se escribe algo descifrado a disco? (SEG-01, SEG-07)
- [ ] ¿Algún import de red (`requests`, `urllib`, `socket`, `http`) fuera de `infrastructure/model_fetcher.py` e `infrastructure/dataset_fetcher.py`? (SEG-20)
- [ ] ¿Los modelos se obtienen solo con `ModelRegistry.verified_path`? (SEG-17, SEG-19)
- [ ] ¿Los fixtures son sintéticos y no hay binarios reales en el diff? (SEG-10)
- [ ] ¿Se capturan excepciones genéricas fuera de `cli/main.py`? (ARQUITECTURA §6)
- [ ] ¿Versiones fijadas con `==` y `uv.lock` actualizado? (SEG-23)
- [ ] Web: ¿bind distinto de 127.0.0.1, endpoint `def` síncrono que use la BD de la sesión, ruta `/api/*` sin la dependencia de sesión, respuesta sin las cabeceras de SEG-28, log de acceso activo o recurso de CDN en el frontend? (SEG-28, ADR-016)
- [ ] ¿Se lee o guarda algún metadato de ubicación u hora de grabación? ¿Se persiste algún recorte que no sea el de la placa? ¿Hay cotejo con listas o alertas? (SEG-29, ADR-017)
- [ ] ¿`.gitignore` sigue cubriendo datos, modelos, logs, videos y `.env`? (SEG-11)
