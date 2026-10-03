# 055 - Exportar el dataset de legibilidad

## Objetivo
Añadir `lector dataset export-legibility`, que exporta **todos** los avistamientos con estado final (confirmados,
corregidos, borrosos y descartados) con su recorte, una clase de legibilidad y las métricas del consolidador. Es el
dataset con el que la spec 057 entrenará el filtro de legibilidad (docs/08 §2).

Es **urgente**: los recortes cifrados caducan por retención (`crops_days` = 90 de forma temporal) y los primeros, del
2026-09-26, se borran el **2026-12-25**. `export-reviewed` (spec 035) no sirve: solo exporta las legibles.

## Depende de
035, 052.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-07 (excepción controlada, ampliada a esta exportación), SEG-03 (retención
  `training_days`), SEG-04 (0700/0600), SEG-05 y SEG-26 (sin texto de placa en consola, logs, auditoría ni errores),
  SEG-06 (el hash del video no sale de la BD), SEG-13 (`resolve_within`).
- docs/02-contratos.md §4 (`LegibilitySample`, `LegibilityExportStore`, `PlateRepository.run_video_hashes`) y §5
  (`ExportLegibilityDataset`, cambio en la purga).
- docs/08-plan-legibilidad-y-web.md §2. ADR-005 (actualización 2026-10-03).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py` (`LegibilityLabel`, `LegibilitySample`, `LegibilityExportStore`,
  método nuevo en `PlateRepository`)
- `src/lector_placas/application/export_legibility.py` (nuevo)
- `src/lector_placas/application/purge_expired.py`
- `src/lector_placas/adapters/export/legibility_export_store.py` (nuevo)
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py` (`run_video_hashes`)
- `src/lector_placas/cli/composition.py` (`LEGIBILITY_EXPORT_DIR`, `build_legibility_store`, `build_purge`)
- `src/lector_placas/cli/dataset_commands.py` (subcomando `export-legibility`)
- `tests/fixtures/fakes.py` (`InMemoryPlateRepository.run_video_hashes`)
- `tests/unit/application/test_export_legibility.py` (nuevo)
- `tests/unit/application/test_purge_legibility.py` (nuevo)
- `tests/unit/adapters/test_legibility_export_store.py` (nuevo)
- `tests/integration/test_run_video_hashes.py` (nuevo)
- `tests/unit/cli/test_export_legibility_cli.py` (nuevo)

No se toca `config/lector.yaml`: se reutiliza `retention.training_days` (180).

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `application/ports.py` (añadir tras `TrainingExportStore`)
- `class LegibilityLabel(StrEnum)` con los valores `LEGIBLE = "legible"`, `BLURRY = "borrosa"`,
  `NOT_PLATE = "no_placa"`.
- `@dataclass(frozen=True, slots=True) class LegibilitySample` con, en este orden: `image: ImageBGR`,
  `label: LegibilityLabel`, `status: ReviewStatus`, `human_reviewed: bool`, `video_group: int`, `run_id: int`,
  `track_id: int`, `vehicle_type: VehicleType`, `confidence: float`, `agreement: float`, `num_readings: int`,
  `reasons: tuple[UnverifiedReason, ...]`. **No lleva texto de placa.** `__post_init__` exige `video_group >= 1`,
  `run_id >= 1`, `track_id >= 0` y `num_readings >= 0`; si no, `ValueError`.
- `class LegibilityExportStore(Protocol)` con `write_samples(self, samples: Sequence[LegibilitySample],
  created_at: datetime) -> Path` y `delete_older_than(self, cutoff: datetime) -> int`.
- `PlateRepository` gana `run_video_hashes(self) -> dict[int, str]`: para **todas** las corridas existentes, su `run_id`
  → `video_sha256`.

### `application/export_legibility.py` (nuevo)
- `PAGE_SIZE: Final[int] = 500`.
- `LABELS: Final[dict[ReviewStatus, LegibilityLabel]]`: `CONFIRMED` y `CORRECTED` → `LEGIBLE`; `ILLEGIBLE` → `BLURRY`;
  `REJECTED` → `NOT_PLATE`. El orden de recorrido es ese: `CONFIRMED`, `CORRECTED`, `ILLEGIBLE`, `REJECTED`.
  `UNVERIFIED` nunca se exporta.
- `@dataclass(frozen=True, slots=True) class ExportLegibilityResult` con `path: Path`, `exported: int`, `skipped: int`
  y `per_label: dict[LegibilityLabel, int]` (las tres clases siempre presentes, aunque valgan 0).
- `class ExportLegibilityDataset` con `__init__(self, repository: PlateRepository, crop_store: CropStore,
  legibility_store: LegibilityExportStore, clock: Clock)` y `execute(self) -> ExportLegibilityResult`.

### `application/purge_expired.py`
`PurgeExpiredData.__init__` gana, al final, `legibility_store: LegibilityExportStore | None = None`.
`RetentionPolicy` y `PurgeResult` **no cambian**.

### `adapters/export/legibility_export_store.py` (nuevo)
Constantes `DIR_PREFIX = "legibility-"`, `ANNOTATIONS_FILE = "annotations.csv"`, `IMAGES_DIR = "images"` y
`class FilesystemLegibilityExportStore` con `__init__(self, root: Path)`, `write_samples` y `delete_older_than`
(firmas del protocolo).

### `cli/composition.py` y `cli/dataset_commands.py`
- `LEGIBILITY_EXPORT_DIR: Final[Path] = Path("training/legibility/datasets/own")`.
- `build_legibility_store(config: AppConfig) -> FilesystemLegibilityExportStore`.
- `cmd_export_legibility(args: argparse.Namespace, config: AppConfig) -> int`.

## Comportamiento esperado

1. **`ExportLegibilityDataset.execute()`**
   - `now = clock.now()`; `hashes = repository.run_video_hashes()`.
   - **Grupos de video:** los hashes distintos se numeran 1, 2, 3… en orden del menor `run_id` de cada hash. Dos
     corridas del mismo video comparten grupo. Así la spec 057 puede repartir por video sin que el hash salga de la BD
     (SEG-06).
   - Para cada estado, en el orden de `LABELS`, pagina `repository.list_sightings(estado, PAGE_SIZE, offset)` hasta
     recibir menos de `PAGE_SIZE`.
   - Por registro: si `crop_ref is None` o `crop_store.load` lanza `CropNotFoundError` → `skipped += 1`. Si su `run_id`
     no está en `hashes` → `ExportError("corrida sin video")`. Si no, crea un `LegibilitySample` con la imagen, la clase
     de `LABELS`, `status`, `human_reviewed = record.reviewed_at is not None`, el grupo de su video y los campos del
     registro.
   - `path = legibility_store.write_samples(muestras, now)`; `repository.log_event(AuditEvent.EXPORT, now, detail)` con
     `detail = f"legibilidad filas={n} omitidos={skipped} legibles={a} borrosas={b} no_placa={c} carpeta={path.name}"`
     y `logger.info` con el mismo `detail`. Devuelve el resultado.
   - Las confirmadas automáticas (`reviewed_at is None`) se exportan como `legible` con `human_reviewed = False`: la
     spec 057 decide si las usa.

2. **`FilesystemLegibilityExportStore.write_samples(samples, created_at)`**
   - Igual que `FilesystemTrainingExportStore` (spec 035) en: `ensure_private_dir(root)`; nombre
     `f"{DIR_PREFIX}{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}"` resuelto con `resolve_within`; si ya existe →
     `ExportError("ya existe una exportación con ese nombre")`; directorio y `images/` con 0700; cada imagen como PNG
     `images/{i:06d}.png` abierta con `O_WRONLY | O_CREAT | O_EXCL` y 0600; fallo de `cv2.imencode` u `OSError` →
     `ExportError` sin texto de placa. Se puede extraer a un módulo común lo compartido con la spec 035 siempre que los
     tests de la 035 sigan pasando sin cambios.
   - `annotations.csv` (0600, `O_EXCL`, UTF-8, `lineterminator="\n"`) con la cabecera, en este orden:
     `image_path,label,status,human_reviewed,video_group,run_id,track_id,vehicle_type,confidence,agreement,num_readings,reasons,crop_width,crop_height`.
     Valores: `label`, `status`, `vehicle_type` y cada razón por su `.value`; `human_reviewed` como `1`/`0`;
     `confidence` y `agreement` con 4 decimales (`f"{x:.4f}"`); `reasons` unidas por `|` (vacío si no hay);
     `crop_width`/`crop_height` = `image.shape[1]`/`image.shape[0]`.
   - Devuelve la ruta del directorio creado.

3. **`delete_older_than(cutoff)`**: idéntico al de la spec 035, pero sobre `root.glob(f"{DIR_PREFIX}*")`.

4. **Purga:** si `legibility_store` no es `None`, se llama a su `delete_older_than` con el **mismo** corte que el de
   entrenamiento (`now - training_days`), justo después de él, y su resultado **se suma** a `training_deleted`. El
   `detail` de auditoría no cambia de formato. Con `None`, el comportamiento es idéntico al actual.

5. **Repositorio SQLCipher:** `run_video_hashes()` hace `SELECT run_id, video_sha256 FROM runs` y devuelve el dict;
   `sqlcipher.Error` → `RepositoryError("run_video_hashes falló")`. El fake `InMemoryPlateRepository` lo implementa con
   `self.runs`.

6. **Composición:** `build_legibility_store(config)` →
   `FilesystemLegibilityExportStore(resolve_within(config.root_dir, LEGIBILITY_EXPORT_DIR))`. `build_purge` pasa además
   `legibility_store=build_legibility_store(config)`.

7. **CLI:** en `register_dataset_commands`, subcomando `dataset export-legibility` sin argumentos, con
   `set_defaults(handler=cmd_export_legibility, network=False, key="load")`. `cmd_export_legibility` sigue el patrón de
   `cmd_export_reviewed` (`commands._run_with_repository`) y escribe en `sys.stdout`
   `f"exportados={r.exported} omitidos={r.skipped} legibles={a} borrosas={b} no_placa={c} carpeta={r.path.name}\n"`.
   Devuelve 0.

## Casos borde y manejo de errores
- Sin avistamientos con estado final: crea la carpeta con `annotations.csv` solo con la cabecera.
- `unverified` nunca aparece en la exportación, aunque tenga recorte.
- Ni la consola, ni los logs, ni `audit_log`, ni los mensajes de error, ni el CSV contienen texto de placa (`ocr_text`
  y `plate_text` no se exportan) ni el hash del video.
- La carpeta `training/legibility/` aún no existe (la crea la spec 057 como proyecto uv): `ensure_private_dir` crea la
  ruta. `training/**/datasets/` ya está en `.gitignore`.

## Tests de aceptación (en prosa)
El implementador escribe estos tests con fixtures sintéticos (SEG-10): imágenes de numpy y placas inventadas.

`tests/unit/application/test_export_legibility.py`, con `InMemoryPlateRepository`, `InMemoryCropStore`, `FakeClock`
y un almacén falso que guarda las muestras recibidas:
- `test_exports_final_statuses_with_labels`: con un avistamiento de cada estado (confirmado, corregido, borroso,
  descartado y uno `unverified`), todos con recorte, se exportan 4 muestras en el orden confirmado, corregido, borroso,
  descartado, con las clases `legible`, `legible`, `borrosa`, `no_placa`; el `unverified` no aparece.
  `per_label` = {legible: 2, borrosa: 1, no_placa: 1}.
- `test_human_reviewed_flag`: un confirmado automático tiene `human_reviewed` falso; uno confirmado en la revisión
  (`record_review`), verdadero.
- `test_skips_missing_crops`: un registro sin `crop_ref` y otro cuyo recorte no está en el almacén cuentan en
  `skipped` y no se exportan.
- `test_video_groups_follow_first_run`: tres corridas, la 1 y la 3 del mismo video y la 2 de otro; las muestras de las
  corridas 1 y 3 tienen grupo 1 y las de la 2, grupo 2.
- `test_audit_and_log_without_plate_text`: el último evento es `EXPORT`; su detalle contiene `filas=`, `omitidos=`,
  `legibles=`, `borrosas=`, `no_placa=` y el nombre de la carpeta, y no contiene ninguna de las placas usadas ni ningún
  hash de video. Lo mismo para el log capturado con `caplog`.
- `test_paginates`: con `PAGE_SIZE` parcheado a 2 y 5 confirmados, se exportan los 5.

`tests/unit/adapters/test_legibility_export_store.py`, en `tmp_path`:
- `test_writes_private_dataset`: el nombre de la carpeta es `legibility-20260926T120000Z`; la cabecera del CSV es
  exactamente la del comportamiento 2; una fila tiene `human_reviewed` `1`, la confianza con 4 decimales, las razones
  unidas por `|` y el ancho y alto del recorte; el PNG leído con `cv2.imread` es igual a la imagen; archivos 0600 y
  directorios (raíz, carpeta e `images`) 0700; escribir otra vez con la misma fecha lanza `ExportError`.
- `test_empty_export_has_header_only`.
- `test_no_plate_text_in_csv`: escribiendo muestras de avistamientos con placas inventadas (`ABC123`, `XYZ98K`), el
  texto completo de `annotations.csv` no contiene ninguna de ellas.
- `test_delete_older_than`: con la raíz inexistente devuelve 0; de dos conjuntos, el que tiene `mtime` de hace 200 días
  se borra con un corte de 180 días y el otro se conserva; no toca carpetas `reviewed-*` de la misma raíz.

`tests/unit/application/test_purge_legibility.py`:
- `test_purge_adds_legibility_to_training_count`: con un almacén de entrenamiento que borra 2 y uno de legibilidad que
  borra 3, `training_deleted` es 5 y ambos reciben el corte `START - 180 días`; el detalle de auditoría termina en
  `entrenamiento=5`.
- `test_purge_without_legibility_store`: sin el parámetro, el resultado es el de antes.

`tests/integration/test_run_video_hashes.py`, con el repositorio SQLCipher real sobre `tmp_path` (mismo arranque que
`tests/integration/test_sqlcipher_repository.py`):
- `test_returns_hash_per_run`: dos corridas con hashes sintéticos distintos devuelven el dict `run_id → hash`; sin
  corridas, dict vacío.

`tests/unit/cli/test_export_legibility_cli.py`:
- `test_parser_registers_export_legibility`: `dataset export-legibility` se analiza con `key == "load"` y
  `network is False`.
- `test_legibility_store_under_training`: `build_legibility_store` sobre la config del repo apunta a
  `<root>/training/legibility/datasets/own`.

## Fuera de alcance
- Volver `retention.crops_days` a 30: es un paso del operador **después** de ejecutar la exportación con datos reales
  y comprobar el conteo (docs/08 §2.2, SEG-03).
- Calcular nitidez o contraste (spec 056) y entrenar el filtro (spec 057): se pueden derivar del PNG exportado.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde; los tests de la spec 035 sin cambios.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] Ningún `print`/log/auditoría/error con texto de placa ni hash de video (checklist de reglas-seguridad.md §8).
