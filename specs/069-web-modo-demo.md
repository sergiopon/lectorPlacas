# 069 - Web: modo demo sintético (`lector-web --demo`)

## Objetivo
`lector-web --demo` arranca la web sobre una carpeta temporal con una BD SQLCipher y recortes cifrados **sintéticos**
(placas inventadas dibujadas con OpenCV) y un procesamiento simulado. Sirve para diseñar, para las pruebas E2E
(spec 071) y para las capturas del README, sin usar la clave del keyring ni ningún dato real.

## Depende de
059, 061, 066, 067, 068.

## Archivos rectores aplicables
- ADR-016 (decisión 8), reglas-seguridad.md SEG-04, SEG-09, SEG-10 (datos sintéticos), SEG-28.
- docs/08-plan-legibilidad-y-web.md §4.4. Decisión de esta spec: los recortes se generan en `src/` con
  `cv2.putText` (fuente Hershey incluida en OpenCV, sin archivos de fuente) en vez de versionar imágenes generadas en
  `training/`; no se generan JSON de muestra (el Anexo A de docs/08 ya trae sus datos ficticios).

## Archivos a crear/modificar
- `src/lector_placas/web/demo.py` (nuevo)
- `src/lector_placas/web/app.py` (opción `--demo`)
- `tests/unit/web/test_demo.py` (nuevo)
- `tests/unit/web/test_app.py` (un test nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados (`web/demo.py`)
- Constantes: `DEMO_SEED: Final[int] = 2026`;
  `def demo_start(now: datetime) -> datetime` → `now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=2)`
  (sustituye a la antigua constante `DEMO_START`: con una fecha fija, la purga por retención de `open_web_session` borraba
  la demo en cuanto la fecha quedaba a más de 90 días);
  `DEMO_PROFILES: Final[tuple[str, ...]] = ("parqueadero", "calle_lenta", "calle_rapida", "patrulla", "calle_lenta")`;
  `DEMO_VIDEOS: Final[tuple[str, ...]] = ("demo_entrada.mp4", "demo_calle.mp4", "demo_patrulla.mp4")`;
  `LETTERS: Final[str] = "ABCDEFGHJKLMNPRSTUVWXYZ"`; `DIGITS: Final[str] = "0123456789"`;
  `PLATE_SIZE: Final[tuple[int, int]] = (300, 100)` (ancho, alto); `PLATE_BGR: Final[tuple[int, int, int]] = (0, 204, 255)`.
- `class DemoKeyProvider` (implementa `KeyProvider`): genera `secrets.token_bytes(32)` en `__init__` y la devuelve en
  `master_key()`.
- `def render_plate(text: str) -> ImageBGR`.
- `def plate_text(rng: random.Random, vehicle_type: VehicleType) -> str`.
- `def create_demo_root() -> Path`: `Path(tempfile.mkdtemp(prefix="lector-demo-"))`, con `chmod(0o700)`, y crea dentro
  `videos/` (0700) con un archivo por nombre de `DEMO_VIDEOS`, cada uno con el contenido `b"lectorPlacas demo\n"` y
  modo 0600.
- `def demo_config(config: AppConfig, root: Path) -> AppConfig` → `config.model_copy(update={"root_dir": root})`.
- `def seed_demo(config: AppConfig, keys: KeyProvider) -> None`.
- `def demo_runner(config: AppConfig, keys: KeyProvider) -> JobRunner`.

## Comportamiento esperado

### 1. `render_plate(text)`
1. `imagen = np.full((100, 300, 3), PLATE_BGR, np.uint8)`.
2. `cv2.rectangle(imagen, (2, 2), (297, 97), (0, 0, 0), 4)`.
3. `rotulo = f"{text[:3]} {text[3:]}"`; `(w, h), _ = cv2.getTextSize(rotulo, cv2.FONT_HERSHEY_SIMPLEX, 1.6, 4)`;
   `cv2.putText(imagen, rotulo, ((300 - w) // 2, (100 + h) // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 4, cv2.LINE_AA)`.
4. Devuelve `imagen`.

### 2. `plate_text(rng, vehicle_type)`
Carro, bus y camión: 3 letras de `LETTERS` y 3 dígitos de `DIGITS`, cada carácter con `rng.choice`, en ese orden.
Moto: 3 letras, 2 dígitos y 1 letra. Ningún texto se compara con placas reales: son inventados (SEG-10).

### 3. `seed_demo(config, keys)`
Con `start = demo_start(datetime.now(UTC))`, `rng = random.Random(DEMO_SEED)` (única excepción permitida: `# noqa: S311 — datos de demo deterministas, no criptográficos (spec 069)` en esa línea), `repository = composition.build_repository(config, keys)` y
`crop_store = composition.build_crop_store(config, keys)`; el repositorio se cierra al final (`try/finally`).
1. **Corridas.** Para `n` de 1 a 5: `start_run(RunStart(hashlib.sha256(f"demo-{n}".encode()).hexdigest(),
   DEMO_PROFILES[n - 1], VideoInfo(1920, 1080, 0, 60_000 * n, 30.0, "h264"), start + timedelta(hours=n)))`.
2. **Avistamientos.** Para `i` de 0 a 39, en orden: `run_id = i // 8 + 1`; `k = i % 8`;
   `vehicle_type = MOTORCYCLE if i % 5 == 4 else CAR`; `texto = plate_text(rng, vehicle_type)`;
   `first = k * 7000`; `last = first + rng.randint(500, 4000)`; `num = rng.randint(2, 8)`;
   `agreement = round(rng.uniform(0.5, 1.0), 2)`.
   - `k` en {3, 4} → **confirmado**: `ConsolidatedPlate(texto, round(rng.uniform(0.90, 0.99), 3), agreement, num,
     CONFIRMED, (), ())`.
   - Resto → **sin confirmar**: `ConsolidatedPlate(guardado, round(rng.uniform(0.55, 0.89), 3), agreement, num,
     UNVERIFIED, (razón,), ())` con `razón = list(UnverifiedReason)[i % 8]`; `guardado = texto`, salvo con `k == 5`, en
     que `guardado` es `texto` con su primer carácter sustituido por el siguiente de `LETTERS` (el último pasa al
     primero).
   - Recorte: `crop_ref = crop_store.save(render_plate(guardado o texto))`; calidad
     `CropQuality(300, 100, round(rng.uniform(20.0, 200.0), 1), round(rng.uniform(20.0, 80.0), 1))`.
   - `save_sighting(Sighting(run_id, i, first, last, vehicle_type, plate, crop_ref, start + timedelta(hours=run_id), quality))`.
   - Revisión, con `reviewed_at = start + timedelta(days=1)`: `k == 5` → `record_review(id, CORRECTED, texto, …)`;
     `k == 6` → `REJECTED`; `k == 7` → `ILLEGIBLE`.
3. **Duplicados.** Dos avistamientos más, `i = 40` y `i = 41`, sin confirmar, que copian texto, vehículo, corrida,
   razón y recorte del avistamiento `i = 1` y del `i = 9`, con `track_id` 40 y 41, `first = 60_000`,
   `last = 61_000`, confianza 0.6, acuerdo 0.6 y 2 lecturas; después `mark_duplicates([(id40, id1), (id41, id9)])`.
4. **Cierre de corridas.** Para cada corrida `n`: `finish_run(n, RunStats(1800 * n, 900 * n, total + 2, confirmados,
   sin_confirmar, 2, 50_000 * n, 60_000 * n), start + timedelta(hours=n, minutes=1), True)`, donde `confirmados`
   y `sin_confirmar` cuentan lo guardado en esa corrida (incluidos los dos duplicados del paso 3, que son `UNVERIFIED` y van a las corridas 1 y 2) con estado `CONFIRMED` y `UNVERIFIED` al guardarse, y
   `total = confirmados + sin_confirmar`.

### 4. `demo_runner(config, keys)`
Devuelve un `JobRunner` que, al llamarse con `(video, profile, reporter)`:
1. Para `paso` de 1 a 20: si `reporter.cancel_requested()` → `ProcessingCancelledError("procesamiento cancelado por el operador")`;
   `reporter.report(ProgressUpdate(paso * 30, paso * 15, paso * 1000, 20_000, paso // 4))`; `time.sleep(0.2)`.
2. Abre `repository = composition.build_repository(config, keys)` (conexión propia, cerrada en `finally`),
   `run_id = repository.start_run(RunStart(sha256_file(video), profile, VideoInfo(1920, 1080, 0, 20_000, 30.0, "h264"), datetime.now(UTC)))`
   y `finish_run(run_id, RunStats(600, 300, 0, 0, 0, 0, 4000, 20_000), datetime.now(UTC), True)`. Devuelve `run_id`.

### 5. `lector-web --demo` (`web/app.py`)
`parse_args` añade `--demo` (`store_true`). En `main`, si `args.demo`:
1. Igual que sin demo hasta `configure_logging`, pero **sin** leer el keyring: `keys = DemoKeyProvider()`.
2. `root = create_demo_root()`; `config_demo = demo_config(config, root)`; `seed_demo(config_demo, keys)`.
3. `network_guard.block_network()`, puerto y token como en la spec 068; `create_app(config_demo, keys, auth, …,
   runner=demo_runner(config_demo, keys), static_dir=config.under_root(FRONTEND_DIST))` (el frontend sale de la raíz
   real; los datos, de la temporal).
4. La salida estándar añade una primera línea `Modo demo: datos sintéticos en una carpeta temporal`.
5. Al terminar el servidor (o ante cualquier error a partir del paso 2), `shutil.rmtree(root)` en un `finally`.

## Casos borde y manejo de errores
- El modo demo nunca abre `data/` real ni el keyring; la carpeta temporal se borra al salir.
- La clave de demo vive solo en memoria.

## Tests de aceptación (en prosa)
`tests/unit/web/test_demo.py`:
- `test_render_plate`: `render_plate("ABC123")` tiene forma `(100, 300, 3)`, `dtype` `uint8`, el píxel de la fila 10, columna 150 es
  `PLATE_BGR` y hay al menos un píxel `(0, 0, 0)` en la franja central (filas 30–70, columnas 40–260).
- `test_plate_text_formats`: con `random.Random(1)`, 50 textos de `CAR` cumplen `^[A-Z]{3}[0-9]{3}$` y 50 de
  `MOTORCYCLE` cumplen `^[A-Z]{3}[0-9]{2}[A-Z]$`; ninguno contiene `I`, `O` ni `Q`.
- `test_create_demo_root`: la carpeta existe con modo 0700 y tiene los tres videos de `DEMO_VIDEOS` con 18 bytes y
  modo 0600; se borra al final del test.
- `test_seed_demo_contents` (integración: SQLCipher real en la carpeta de demo, `DemoKeyProvider`): tras `seed_demo`,
  con un repositorio nuevo sobre la misma carpeta y la misma clave hay 5 corridas, 42 avistamientos, 2 con
  `duplicate_of` no nulo, los conteos por estado son `unverified` 17, `confirmed` 10, `corrected` 5, `rejected` 5,
  `illegible` 5, todos con `crop_ref` cargable y `quality` no nula; ejecutarlo dos veces con dos carpetas distintas da
  los mismos textos de placa en el mismo orden (determinista).
- `test_demo_survives_purge` (integración): tras `seed_demo` en la carpeta de demo, `open_web_session(config_demo, keys)`
  (que purga por retención) deja los 42 avistamientos y las 5 corridas; se cierra la sesión al final.
- `test_demo_start`: `demo_start(datetime(2026, 10, 4, 16, 45, 9, tzinfo=UTC)) == datetime(2026, 10, 2, 16, 0, tzinfo=UTC)`.
- `test_demo_runner_progress_and_cancel`: con un reporter que registra los `ProgressUpdate` y `time.sleep` parcheado a no
  hacer nada, el runner sobre la carpeta de demo reporta 20 actualizaciones y devuelve un `run_id` 6 tras sembrar; con un
  reporter que pide cancelar desde el inicio lanza `ProcessingCancelledError` sin reportar nada.

`tests/unit/web/test_app.py` (añadir):
- `test_main_demo_mode`: con los mismos parches que `test_main_happy_path` (spec 068) más
  `lector_placas.web.app.seed_demo` (registra la config recibida) y sin parchear `build_key_provider` sino haciéndolo
  fallar si se llama, `main(["--demo", "--no-browser"])` devuelve 0, no llamó a `build_key_provider`, `create_app`
  recibió una config cuyo `root_dir` empieza por el directorio temporal del sistema y contiene `lector-demo-`, la salida
  empieza por `Modo demo: datos sintéticos en una carpeta temporal` y esa carpeta ya no existe al volver.

## Fuera de alcance
- Capturas y GIF del README (spec 072).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `uv run lector-web --help` muestra `--demo`.
