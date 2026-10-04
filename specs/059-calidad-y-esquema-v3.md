# 059 - Calidad del mejor recorte por avistamiento, `duplicate_of` y esquema v3

## Objetivo
Guardar por avistamiento el tamaño (ancho y alto en píxeles), la nitidez y el contraste de su mejor recorte, y preparar
la columna `duplicate_of` que usará la spec 061. Requiere migrar la BD del esquema v2 al v3 con la receta de la spec 052.
El dataset de legibilidad (spec 055) añade estas medidas y el tamaño del frame de la corrida.

## Depende de
052, 055, 057.

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §1.5, §3.4 y §4.2; ADR-017 (decisión 4).
- docs/03-modelo-datos.md §2 (esquema; lo actualiza el orquestador) y docs/02-contratos.md §3–§4.
- reglas-seguridad.md SEG-04, SEG-05, SEG-07, SEG-15 (SQL literal y parametrizado).
- CLAUDE.md: receta de migración (tabla nueva, copia, renombrado, índices, versión, todo en `BEGIN IMMEDIATE`).

## Archivos a crear/modificar
- `src/lector_placas/domain/entities.py` (`CropQuality`; campos nuevos en `Sighting` y `SightingRecord`)
- `src/lector_placas/application/image_ops.py` (`rms_contrast`)
- `src/lector_placas/application/process_video.py` (calcula la calidad al guardar)
- `src/lector_placas/application/ports.py` (`PlateRepository.run_frame_sizes`; campos nuevos de `LegibilitySample`)
- `src/lector_placas/application/export_legibility.py`
- `src/lector_placas/adapters/persistence/schema.sql`
- `src/lector_placas/adapters/persistence/migrations.py` (`migrate_v2_to_v3`)
- `src/lector_placas/adapters/persistence/rows.py`
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py`
- `src/lector_placas/adapters/persistence/sqlcipher_browser.py`
- `src/lector_placas/adapters/export/legibility_export_store.py`
- `tests/fixtures/fakes.py`
- `tests/unit/domain/test_crop_quality.py` (nuevo)
- `tests/unit/application/test_image_ops_contrast.py` (nuevo)
- `tests/unit/application/test_process_video_quality.py` (nuevo)
- `tests/integration/test_schema_v3.py` (nuevo)
- `tests/integration/test_schema_migration.py` (un cambio de expectativa, ver Tests)
- `tests/unit/adapters/test_legibility_export_store.py` (un cambio de expectativa y un test nuevo)
- `tests/unit/application/test_export_legibility.py` (un test nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `domain/entities.py`
- Nueva `@dataclass(frozen=True, slots=True) class CropQuality` con `plate_width_px: int`, `plate_height_px: int`,
  `sharpness: float`, `contrast: float`. `__post_init__`: `plate_width_px >= 1` y `plate_height_px >= 1`, si no
  `InvalidEntityError(f"{nombre} debe ser >= 1: {valor}")`; `sharpness` y `contrast` finitos y `>= 0.0`, si no
  `InvalidEntityError(f"{nombre} debe ser finito y >= 0: {valor}")`.
- `Sighting` gana, **al final**, `quality: CropQuality | None = None`.
- `SightingRecord` gana, **al final** y en este orden, `quality: CropQuality | None = None` y
  `duplicate_of: int | None = None`. `__post_init__` añade al final: si `duplicate_of` no es `None`, debe ser `>= 1` y
  distinto de `sighting_id`; si no, `InvalidEntityError("duplicate_of inválido")`.

### `application/image_ops.py`
`def rms_contrast(image: ImageBGR) -> float`: convierte a luminancia en `float64` con
`gris = 0.114 * B + 0.587 * G + 0.299 * R` (canales en orden BGR: `image[..., 0]`, `image[..., 1]`, `image[..., 2]`) y
devuelve `float(np.std(gris))` (desviación típica poblacional, `ddof=0`).

### `application/ports.py`
- `PlateRepository` gana `run_frame_sizes(self) -> dict[int, tuple[int, int]]`: para todas las corridas, `run_id` →
  `(width, height)` tal como se guardaron en `runs` (ya rotados, `VideoInfo`).
- `LegibilitySample` gana, **al final** y en este orden, con valor por defecto `None`: `plate_width_px: int | None`,
  `plate_height_px: int | None`, `sharpness: float | None`, `contrast: float | None`, `frame_width: int | None`,
  `frame_height: int | None`.

### `adapters/persistence/migrations.py`
`def migrate_v2_to_v3(connection: sqlcipher.Connection) -> None`, con la misma estructura que `migrate_v1_to_v2`
(`PRAGMA foreign_keys = OFF`, `isolation_level = None`, transacción `BEGIN IMMEDIATE` con `ROLLBACK` protegido,
`_check_foreign_keys` al final) y el log `logger.info("esquema migrado de v2 a v3 avistamientos=%d", count)`.

## Comportamiento esperado

### 1. Esquema v3 de `sightings`
Mismas columnas y restricciones que v2, más estas cinco **al final** (después de `reviewed_at`), en este orden:
- `plate_width_px  INTEGER CHECK (plate_width_px IS NULL OR plate_width_px >= 1)`
- `plate_height_px INTEGER CHECK (plate_height_px IS NULL OR plate_height_px >= 1)`
- `sharpness       REAL    CHECK (sharpness IS NULL OR sharpness >= 0.0)`
- `contrast        REAL    CHECK (contrast IS NULL OR contrast >= 0.0)`
- `duplicate_of    INTEGER REFERENCES sightings(sighting_id) ON DELETE SET NULL CHECK (duplicate_of IS NULL OR duplicate_of <> sighting_id)`

Y una restricción de tabla nueva, después de `UNIQUE (run_id, track_id, first_seen_ms)`:
`CHECK ((plate_width_px IS NULL) = (plate_height_px IS NULL) AND (plate_width_px IS NULL) = (sharpness IS NULL) AND (plate_width_px IS NULL) = (contrast IS NULL))`.
Índice nuevo: `CREATE INDEX IF NOT EXISTS idx_sightings_duplicate_of ON sightings(duplicate_of) WHERE duplicate_of IS NOT NULL`.

`schema.sql` pasa a crear directamente la tabla v3 y el índice nuevo. `SCHEMA_VERSION` (repositorio) pasa a `3`.

### 2. Migración
- `migrate_v2_to_v3`: crea `sightings_v3` con el DDL v3, copia todas las filas con una lista de columnas fija
  (las 18 de v2; las 5 nuevas quedan `NULL`), `DROP TABLE sightings`, `ALTER TABLE sightings_v3 RENAME TO sightings`,
  recrea los cinco índices (los cuatro de v2 y `idx_sightings_duplicate_of`), `UPDATE schema_version SET version = 3`
  y `COMMIT`. Cualquier `sqlcipher.Error` → `RepositoryError("migración de esquema fallida")` y la BD queda en v2.
- `_check_schema_version` del repositorio: versión 1 → `migrate_v1_to_v2` y después `migrate_v2_to_v3`; versión 2 →
  `migrate_v2_to_v3`; versión 3 → nada; otra → `RepositoryError("versión de esquema no soportada")` (sin cambios). Si
  una migración falla, se cierra la conexión y se relanza (como hoy).

### 3. Lectura y escritura
- Las tres consultas que leen avistamientos completos (`_SELECT_SIGHTINGS_PAGE` y `_SELECT_SIGHTING_BY_ID` del
  repositorio, `_SEARCH_SQL` del navegador) y `SIGHTING_COLUMNS` añaden al final, en este orden,
  `plate_width_px, plate_height_px, sharpness, contrast, duplicate_of`.
- `row_to_record`: si `plate_width_px` es `NULL`, `quality = None`; si no,
  `CropQuality(plate_width_px, plate_height_px, sharpness, contrast)`. `duplicate_of` se copia tal cual.
- `save_sighting` inserta además las cuatro columnas de calidad (`NULL` si `sighting.quality is None`). `duplicate_of`
  no se escribe (queda `NULL`).
- `run_frame_sizes`: `SELECT run_id, width, height FROM runs`; `sqlcipher.Error` →
  `RepositoryError("run_frame_sizes falló")`.
- Fake `InMemoryPlateRepository`: `save_sighting` copia `sighting.quality` al `SightingRecord`; `run_frame_sizes`
  devuelve `{run_id: (run.start.video.width, run.start.video.height)}`.

### 4. `ProcessVideo._save_track`
Si `track.best_crop is not None`:
`quality = CropQuality(best_crop.shape[1], best_crop.shape[0], deps.quality.sharpness(best_crop), rms_contrast(best_crop))`;
si es `None`, `quality = None`. El `Sighting` se crea con `quality=quality`. Nada más cambia.

### 5. Dataset de legibilidad
- `ExportLegibilityDataset` obtiene además `sizes = repository.run_frame_sizes()` y rellena en cada muestra
  `plate_width_px`, `plate_height_px`, `sharpness` y `contrast` desde `record.quality` (todos `None` si es `None`) y
  `frame_width`, `frame_height` desde `sizes[record.run_id]`. Si el `run_id` no está en `sizes` →
  `ExportError("corrida sin video")`.
- La cabecera de `annotations.csv` añade al final, en este orden:
  `plate_width_px,plate_height_px,sharpness,contrast,frame_width,frame_height`. Valores: enteros con `str`; `sharpness` y
  `contrast` con `f"{x:.4f}"`; `None` → cadena vacía.

## Casos borde y manejo de errores
- Avistamientos anteriores a esta spec: calidad `NULL` en BD, `quality = None` en el registro y celdas vacías en el CSV.
- La restricción de tabla impide guardar calidad parcial.
- Borrar un avistamiento al que apunta `duplicate_of` deja `NULL` en el que apuntaba (`ON DELETE SET NULL`).

## Tests de aceptación (en prosa)
Fixtures sintéticos.

**Tests existentes que cambian de expectativa (solo estos):**
- `tests/integration/test_schema_migration.py::test_v1_database_is_migrated_preserving_rows`: la versión tras abrir pasa
  de `2` a `3`. El resto del test no cambia.
- `tests/unit/adapters/test_legibility_export_store.py::test_writes_private_dataset`: la cabecera esperada añade al final
  `plate_width_px,plate_height_px,sharpness,contrast,frame_width,frame_height`. El resto del test no cambia.

`tests/unit/domain/test_crop_quality.py`:
- `test_valid_crop_quality`: `CropQuality(100, 30, 12.5, 40.0)` se crea.
- `test_invalid_crop_quality` (parametrizado): ancho 0, alto 0, nitidez -1.0, contraste -0.5, nitidez `float("nan")` y
  contraste `float("inf")` lanzan `InvalidEntityError`.
- `test_sighting_record_duplicate_of`: un `SightingRecord` con `sighting_id=5` y `duplicate_of=5` lanza
  `InvalidEntityError`; con `duplicate_of=0` también; con `duplicate_of=3` se crea.

`tests/unit/application/test_image_ops_contrast.py`:
- `test_uniform_image_has_zero_contrast`: imagen 10×30×3 con todos los valores 90 → `0.0`.
- `test_half_black_half_white`: imagen 10×20×3 con las columnas 0–9 a 0 y 10–19 a 255 → `127.5` (con
  `pytest.approx(127.5)`).
- `test_channel_weights`: imagen 2×1×3 con el píxel 0 en `(255, 0, 0)` y el píxel 1 en `(0, 0, 0)` → luminancias
  `29.07` y `0.0` → `pytest.approx(14.535)`.

`tests/unit/application/test_process_video_quality.py` (reutiliza `build` y `SHA` de
`tests.unit.application.test_process_video`):
- `test_saved_sighting_has_crop_quality`: con `build([i * 100 for i in range(10)])` el avistamiento guardado tiene
  `quality.plate_width_px == 100`, `quality.plate_height_px == 30`, `quality.sharpness == 50.0` (de `ConstantQuality`)
  y `quality.contrast == 0.0` (el frame de `FakeSource` es uniforme, valor 90).

`tests/integration/test_schema_v3.py` (mismo arranque que `tests/integration/test_schema_migration.py`: repositorio
SQLCipher real en `tmp_path` con `FakeKeyProvider`):
- `test_new_database_is_v3`: una BD nueva tiene `schema_version` 3 y la tabla `sightings` tiene las columnas
  `plate_width_px`, `plate_height_px`, `sharpness`, `contrast` y `duplicate_of` (`PRAGMA table_info`).
- `test_quality_roundtrip`: guardar un avistamiento con `CropQuality(100, 30, 12.5, 40.0)` y otro sin calidad; leerlos
  con `list_sightings` y con `get_sighting` devuelve esa calidad y `None`, y `duplicate_of is None` en ambos; el
  navegador (`search_sightings` con `SightingQuery()`) devuelve las mismas calidades.
- `test_v2_database_is_migrated_to_v3`: crear una BD, guardar dos avistamientos, convertirla a v2 recreando
  `sightings` con el DDL v2 (copiado en el test del `_CREATE_SIGHTINGS_V2` de `migrations.py`, sin las columnas nuevas)
  y `schema_version` 2; al reabrir con el repositorio, `schema_version` es 3, los dos registros son iguales a los de
  antes y el log contiene `esquema migrado de v2 a v3 avistamientos=2`.
- `test_failed_v3_migration_leaves_v2_intact`: tras convertirla a v2, crear una tabla `sightings_v3 (x INTEGER)` para
  que la migración falle; abrir el repositorio lanza `RepositoryError` y, con una conexión cruda, `schema_version`
  sigue en 2 y las filas siguen ahí.
- `test_duplicate_of_set_null_on_delete`: con una conexión cruda, poner `duplicate_of` del avistamiento 2 a 1 y borrar
  el 1 con `foreign_keys = ON`; el 2 queda con `duplicate_of` `NULL`.
- `test_partial_quality_is_rejected`: con una conexión cruda, un `UPDATE` que pone `plate_width_px = 10` dejando
  `sharpness` `NULL` lanza `sqlcipher.IntegrityError`.
- `test_run_frame_sizes`: dos corridas con `VideoInfo` de 1920×1080 y 1280×720 devuelven
  `{1: (1920, 1080), 2: (1280, 720)}`.

`tests/unit/application/test_export_legibility.py` (añadir):
- `test_exports_quality_and_frame_size`: un avistamiento confirmado guardado con `CropQuality(100, 30, 12.5, 40.0)` en
  una corrida de `VideoInfo(1920, 1080, …)` y otro sin calidad; las muestras tienen `plate_width_px == 100`,
  `sharpness == 12.5`, `frame_width == 1920`, `frame_height == 1080` y, en la segunda, `plate_width_px is None`.

`tests/unit/adapters/test_legibility_export_store.py` (añadir):
- `test_quality_columns`: una muestra con `plate_width_px=100`, `plate_height_px=30`, `sharpness=12.5`,
  `contrast=40.0`, `frame_width=1920`, `frame_height=1080` escribe `100,30,12.5000,40.0000,1920,1080` en esas columnas;
  otra con todo `None` escribe seis celdas vacías.

## Fuera de alcance
- Calcular y escribir `duplicate_of` (spec 061).
- Usar la nitidez como umbral (experimento E8, docs/09).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde; solo cambian los dos tests listados.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -nE "execute\(f|execute\(.*%|execute\(.*\+" src/` sin resultados (SEG-15).
