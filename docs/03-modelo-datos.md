# 03 — Modelo de datos, recortes y configuración

## 1. Base de datos (SQLCipher) — `src/lector_placas/adapters/persistence/schema.sql`

- Archivo: `data/lector.db` (permisos 0600, directorio `data/` 0700).
- Apertura: `sqlcipher3.dbapi2.connect(str(path))`, luego `PRAGMA key = "x'<hex>'"` con la subclave
  HKDF `KeyPurpose.SQLCIPHER` (64 hex minúsculas validadas con `^[0-9a-f]{64}$`), luego
  `PRAGMA foreign_keys = ON`, luego verificación `SELECT count(*) FROM sqlite_master` (clave
  incorrecta → `sqlcipher3.dbapi2.DatabaseError` → `EncryptionError`).
- Fechas: texto ISO-8601 UTC con microsegundos, `datetime.isoformat(timespec="microseconds")` sobre un
  `datetime` UTC (ej. `2026-09-24T20:15:03.123456+00:00`). Mismo formato en todas las columnas, por lo
  que las comparaciones lexicográficas son cronológicas.
- Listas (`reasons`, `format_ids`): texto separado por `,` sin espacios; cadena vacía si no hay elementos.
- **Solo consultas parametrizadas** (`?`). Única excepción: `PRAGMA key` (ADR-005).

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    video_sha256           TEXT    NOT NULL CHECK (length(video_sha256) = 64
                                                   AND video_sha256 NOT GLOB '*[^0-9a-f]*'),
    profile                TEXT    NOT NULL CHECK (length(profile) BETWEEN 1 AND 64),
    width                  INTEGER NOT NULL CHECK (width > 0),
    height                 INTEGER NOT NULL CHECK (height > 0),
    rotation_deg           INTEGER NOT NULL CHECK (rotation_deg IN (0, 90, 180, 270)),
    duration_ms            INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    started_at             TEXT    NOT NULL,
    finished_at            TEXT,
    status                 TEXT    NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    frames_decoded         INTEGER CHECK (frames_decoded IS NULL OR frames_decoded >= 0),
    frames_processed       INTEGER CHECK (frames_processed IS NULL OR frames_processed >= 0),
    tracks_total           INTEGER CHECK (tracks_total IS NULL OR tracks_total >= 0),
    sightings_confirmed    INTEGER CHECK (sightings_confirmed IS NULL OR sightings_confirmed >= 0),
    sightings_unverified   INTEGER CHECK (sightings_unverified IS NULL OR sightings_unverified >= 0),
    tracks_without_reading INTEGER CHECK (tracks_without_reading IS NULL OR tracks_without_reading >= 0),
    processing_ms          INTEGER CHECK (processing_ms IS NULL OR processing_ms >= 0)
);

CREATE TABLE IF NOT EXISTS plates (
    plate_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_text    TEXT NOT NULL UNIQUE CHECK (length(plate_text) BETWEEN 1 AND 10
                                              AND plate_text NOT GLOB '*[^A-Z0-9]*'),
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sightings (
    sighting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    plate_id      INTEGER REFERENCES plates(plate_id) ON DELETE SET NULL,
    track_id      INTEGER NOT NULL CHECK (track_id >= 0),
    first_seen_ms INTEGER NOT NULL CHECK (first_seen_ms >= 0),
    last_seen_ms  INTEGER NOT NULL CHECK (last_seen_ms >= first_seen_ms),
    vehicle_type  TEXT    NOT NULL CHECK (vehicle_type IN ('car', 'motorcycle', 'bus', 'truck')),
    ocr_text      TEXT    NOT NULL CHECK (length(ocr_text) BETWEEN 1 AND 10
                                          AND ocr_text NOT GLOB '*[^A-Z0-9]*'),
    plate_text    TEXT    NOT NULL CHECK (length(plate_text) BETWEEN 1 AND 10
                                          AND plate_text NOT GLOB '*[^A-Z0-9]*'),
    confidence    REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    agreement     REAL    NOT NULL CHECK (agreement BETWEEN 0.0 AND 1.0),
    num_readings  INTEGER NOT NULL CHECK (num_readings >= 1),
    status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified', 'rejected', 'corrected', 'illegible')),
    reasons       TEXT    NOT NULL,
    format_ids    TEXT    NOT NULL,
    crop_ref      TEXT CHECK (crop_ref IS NULL OR (length(crop_ref) = 32
                                                   AND crop_ref NOT GLOB '*[^0-9a-f]*')),
    created_at    TEXT    NOT NULL,
    reviewed_at   TEXT,
    plate_width_px  INTEGER CHECK (plate_width_px IS NULL OR plate_width_px >= 1),     -- v3 (spec 059)
    plate_height_px INTEGER CHECK (plate_height_px IS NULL OR plate_height_px >= 1),
    sharpness       REAL    CHECK (sharpness IS NULL OR sharpness >= 0.0),
    contrast        REAL    CHECK (contrast IS NULL OR contrast >= 0.0),
    duplicate_of    INTEGER REFERENCES sightings(sighting_id) ON DELETE SET NULL
                            CHECK (duplicate_of IS NULL OR duplicate_of <> sighting_id),
    UNIQUE (run_id, track_id, first_seen_ms),
    CHECK ((plate_width_px IS NULL) = (plate_height_px IS NULL)
           AND (plate_width_px IS NULL) = (sharpness IS NULL)
           AND (plate_width_px IS NULL) = (contrast IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_sightings_status     ON sightings(status);
CREATE INDEX IF NOT EXISTS idx_sightings_created_at ON sightings(created_at);
CREATE INDEX IF NOT EXISTS idx_sightings_plate_id   ON sightings(plate_id);
CREATE INDEX IF NOT EXISTS idx_sightings_crop_ref   ON sightings(crop_ref) WHERE crop_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sightings_duplicate_of ON sightings(duplicate_of) WHERE duplicate_of IS NOT NULL;  -- v3
CREATE INDEX IF NOT EXISTS idx_runs_started_at      ON runs(started_at);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL CHECK (event IN ('run_started', 'run_finished', 'review', 'purge', 'export')),
    occurred_at TEXT NOT NULL,
    detail      TEXT NOT NULL CHECK (length(detail) <= 500)
);
```

Versión de esquema: `3` (spec 059: calidad del mejor recorte y `duplicate_of`; `migrate_v2_to_v3` sigue la misma receta, y una BD v1 se migra a v2 y luego a v3). Historia: `2` (spec 052). Al abrir, si `schema_version` está vacía se inserta `2`; si es `1` se migra a `2`
(`adapters/persistence/migrations.py`: en una transacción `BEGIN IMMEDIATE` se recrea `sightings` con el `CHECK` de
`status` que admite `'illegible'`, se copian las filas con su `sighting_id`, se recrean sus índices y se pone la versión
a 2; si algo falla, `ROLLBACK` y la BD queda en v1); cualquier otro valor → `RepositoryError("versión de esquema no
soportada")`. v1 = el mismo esquema sin `'illegible'`.

### Semántica de escritura

| Operación | Efecto |
|---|---|
| `start_run` | INSERT en `runs` con `status='running'`; `log_event(RUN_STARTED, "run_id=<id>")` |
| `finish_run` | UPDATE de estadísticas, `finished_at`, `status='completed'` o `'failed'`; `log_event(RUN_FINISHED, "run_id=<id> status=<s>")` |
| `save_sighting` | INSERT con `ocr_text = plate_text = plate.text`. Si `status='confirmed'`: upsert en `plates` (`INSERT ... ON CONFLICT(plate_text) DO UPDATE SET last_seen_at = excluded.last_seen_at`) y `plate_id` enlazado. En otro caso `plate_id = NULL` |
| `record_review` CONFIRMED | `status='confirmed'`, upsert placa con `plate_text` vigente, enlaza `plate_id`, `reviewed_at` |
| `record_review` CORRECTED | `plate_text = corrected_text`, `status='corrected'`, upsert/enlace con el texto corregido, `reviewed_at` |
| `record_review` REJECTED | `status='rejected'`, `plate_id = NULL`, `reviewed_at` |
| `expire_crop_refs(cutoff)` | Para avistamientos con `created_at < cutoff` y `crop_ref` no nulo: devuelve los refs y los pone en NULL (una transacción) |
| `delete_records_before(cutoff)` | Recoge `crop_ref` no nulos de avistamientos con `created_at < cutoff`; los borra; borra `runs` con `started_at < cutoff` sin avistamientos; borra `plates` sin avistamientos; devuelve `RecordPurge` |
| `log_event` | INSERT en `audit_log`. `detail` solo contiene ids, conteos y estados: **nunca texto de placa** |

Todas las operaciones de escritura se ejecutan en una transacción (`with connection:`).

## 2. Recortes cifrados en disco

| Aspecto | Política |
|---|---|
| Qué se guarda | Solo el mejor recorte de placa por avistamiento (mayor `quality_score × mean_confidence`) |
| Formato en claro (solo en memoria) | PNG (`cv2.imencode(".png", image)`), sin pérdida |
| Cifrado | AES-256-GCM, subclave `KeyPurpose.CROPS`, nonce aleatorio de 12 bytes, AAD = `crop_ref` en ASCII |
| Archivo | `data/crops/<crop_ref[0:2]>/<crop_ref>.bin` = `nonce (12 B) ‖ ciphertext+tag` |
| Identificador | `crop_ref = secrets.token_hex(16)` (32 hex minúsculas); no deriva de la placa |
| Permisos | Directorios 0700, archivos 0600; escritura atómica (`<ref>.tmp` con `O_CREAT|O_EXCL`, `fsync`, `os.replace`) |
| Retención | 30 días (`retention.crops_days`); al expirar se borra el archivo y `crop_ref` queda en NULL; además `CropStore.delete_older_than` borra por fecha de modificación cualquier archivo `.bin`/`.tmp` más antiguo (huérfanos) |
| Lectura | Solo la CLI de revisión, en memoria; nunca se escribe descifrado a disco |

## 3. Exportaciones CSV

`data/exports/sightings-<YYYYmmddTHHMMSSZ>.csv` (0600), UTF-8, separador `,`, cabecera fija:
`sighting_id,run_id,track_id,first_seen_ms,last_seen_ms,vehicle_type,plate_text,ocr_text,confidence,agreement,num_readings,status,reasons,format_ids,created_at,reviewed_at`.
Dentro de una celda las listas usan `|`. Toda celda que empiece por `=`, `+`, `-` o `@` se prefija con
`'` (inyección CSV). Se borran tras `retention.records_days` días.

## 4. Configuración — `config/lector.yaml`

Validada con pydantic 2.13.5 (`model_config = ConfigDict(extra="forbid", frozen=True)`), cargada con
`yaml.safe_load`. Todo error → `ConfigurationError` con la ruta del campo. Rutas relativas se resuelven
contra el directorio raíz del proyecto (el padre de `config/`).

```yaml
version: 1

paths:
  data_dir: data
  models_dir: models
  log_dir: logs
  model_manifest: config/models.yaml

input:
  allowed_dirs: [videos]
  allowed_extensions: [".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"]
  max_file_size_mb: 4096

inference:
  execution_provider: cuda            # cuda | cpu

models:
  vehicle_detector:
    model_id: yolo26n-coco
    input_size: 640
    score_threshold: 0.25
  plate_detector:
    backend: open_image_models         # open_image_models | yolo
    model_id: oim-yolo-v9-t-384-plates
    input_size: 384                    # solo se usa con backend yolo
    score_threshold: 0.25
  ocr:
    model_id: fpo-cct-xs-v2-global
    config_id: fpo-cct-xs-v2-global-config

tracker:
  lost_track_buffer: 30
  track_activation_threshold: 0.7
  minimum_consecutive_frames: 2
  minimum_iou_threshold_first_assoc: 0.2
  minimum_iou_threshold_second_assoc: 0.5
  minimum_iou_threshold_unconfirmed_assoc: 0.3
  high_conf_det_threshold: 0.6
  cmc_method: sparseOptFlow            # sparseOptFlow | orb | sift | ecc
  cmc_downscale: 2

default_profile: calle_lenta
profiles:
  parqueadero:
    mode: estatico
    camera_motion_compensation: true
    target_fps: 10
    max_readings_per_track: 8
    track_finalize_after_ms: 3000
    min_readings: 3
    confirm_threshold: 0.90
    min_agreement: 0.60
    min_plate_width_px: 32            # spec 057 (antes 20)
    min_sharpness: 0.0
    max_ocr_per_frame: 8
    vehicle_crop_margin: 0.10
    near_min_width_frac: 0.025        # spec 057: ancho mínimo = ceil(max(min_plate_width_px, frac × lado mayor))
    max_plate_vehicle_ratio: 0.5
    roi: [0.0, 0.0, 1.0, 1.0]         # x1, y1, x2, y2 normalizados sobre el frame rotado
    early_stop: true                  # spec 060
    dedup_window_ms: 30000            # spec 061: [0, 600000]; 0 desactiva
  calle_lenta:
    mode: estatico
    camera_motion_compensation: true
    target_fps: 15
    max_readings_per_track: 8
    track_finalize_after_ms: 2000
    min_readings: 3
    confirm_threshold: 0.90
    min_agreement: 0.60
    min_plate_width_px: 32            # spec 057 (antes 20)
    min_sharpness: 0.0
    max_ocr_per_frame: 8
    vehicle_crop_margin: 0.10
    near_min_width_frac: 0.025        # spec 057: ancho mínimo = ceil(max(min_plate_width_px, frac × lado mayor))
    max_plate_vehicle_ratio: 0.5
    roi: [0.0, 0.0, 1.0, 1.0]         # x1, y1, x2, y2 normalizados sobre el frame rotado
    early_stop: true                  # spec 060
    dedup_window_ms: 30000            # spec 061: [0, 600000]; 0 desactiva
  calle_rapida:
    mode: estatico
    camera_motion_compensation: true
    target_fps: 30
    max_readings_per_track: 6
    track_finalize_after_ms: 1000
    min_readings: 2
    confirm_threshold: 0.90
    min_agreement: 0.60
    min_plate_width_px: 32            # spec 057 (antes 20)
    min_sharpness: 0.0
    max_ocr_per_frame: 8
    vehicle_crop_margin: 0.10
    near_min_width_frac: 0.025        # spec 057: ancho mínimo = ceil(max(min_plate_width_px, frac × lado mayor))
    max_plate_vehicle_ratio: 0.5
    roi: [0.0, 0.0, 1.0, 1.0]         # x1, y1, x2, y2 normalizados sobre el frame rotado
    early_stop: true                  # spec 060
    dedup_window_ms: 30000            # spec 061: [0, 600000]; 0 desactiva
  patrulla:                          # spec 056, modo movil (ADR-017)
    mode: movil
    camera_motion_compensation: true
    target_fps: 30
    max_readings_per_track: 6
    track_finalize_after_ms: 1000
    min_readings: 2
    confirm_threshold: 0.90
    min_agreement: 0.60
    min_plate_width_px: 32            # spec 057 (antes 20)
    min_sharpness: 0.0
    max_ocr_per_frame: 8
    vehicle_crop_margin: 0.10
    near_min_width_frac: 0.025        # spec 057: ancho mínimo = ceil(max(min_plate_width_px, frac × lado mayor))
    max_plate_vehicle_ratio: 0.5
    roi: [0.0, 0.0, 1.0, 1.0]         # x1, y1, x2, y2 normalizados sobre el frame rotado
    early_stop: true                  # spec 060
    dedup_window_ms: 30000            # spec 061: [0, 600000]; 0 desactiva

consolidation:
  ambiguity_margin: 0.10
  confusions: [["O", "0"], ["I", "1"], ["B", "8"], ["S", "5"]]

retention:
  crops_days: 90      # temporal (2026-09-27, docs/08 §2.2); valor normal 30
  records_days: 90
  training_days: 180                 # exportaciones de entrenamiento (spec 035)

logging:
  level: INFO                          # DEBUG | INFO | WARNING | ERROR

plate_formats:
  - {format_id: co_particular_publico, category: "Particular / público / oficial / antiguo / clásico",
     pattern: LLLDDD, regex: "^[A-Z]{3}[0-9]{3}$", verified: true,
     vehicle_types: [car, bus, truck], source: "Res. 708/1991 art. 6; Ficha Técnica MT 001; Res. 3257/2018"}
  - {format_id: co_diplomatico_2015, category: "Diplomático / consular / misiones (diseño 2015)",
     pattern: LLLDDD, regex: "^[MDCAO][A-Z]{2}[0-9]{3}$", verified: true,
     vehicle_types: [car, bus, truck], source: "Res. 1690/2015 (derogada por Res. 6705/2019; cambios NO VERIFICADOS)"}
  - {format_id: co_moto_diplomatica, category: "Moto diplomática", pattern: LLLDDD,
     regex: "^MCD[0-9]{3}$", verified: true, vehicle_types: [motorcycle], source: "Res. 1690/2015 art. 3"}
  - {format_id: co_moto, category: "Motocicleta", pattern: LLLDDL, regex: "^[A-Z]{3}[0-9]{2}[A-Z]$",
     verified: true, vehicle_types: [motorcycle], source: "Res. 4923/1994"}
  - {format_id: co_moto_antigua, category: "Motocicleta (formato antiguo)", pattern: LLLDD,
     regex: "^[A-Z]{3}[0-9]{2}$", verified: true, vehicle_types: [motorcycle], source: "Ficha Técnica MT 001 §4.2"}
  - {format_id: co_motocarro, category: "Motocarro", pattern: DDDLLL, regex: "^[0-9]{3}[A-Z]{3}$",
     verified: true, vehicle_types: [car, motorcycle, bus, truck], source: "Res. 1421/2011"}
  - {format_id: co_diplomatico_antiguo, category: "Diplomático (antiguo, azul)", pattern: LLDDDD,
     regex: "^(CD|CC|AT|OI)[0-9]{4}$", verified: true, vehicle_types: [car, bus, truck],
     source: "Res. 3458/2000 (citada en Res. 1690/2015)"}
  - {format_id: co_remolque, category: "Remolque / semirremolque (placa verde)", pattern: LDDDDD,
     regex: "^[RS][0-9]{5}$", verified: false, vehicle_types: [car, motorcycle, bus, truck],
     source: "Prensa (Semana 2026); sin fuente oficial"}
  - {format_id: co_importacion_temporal, category: "Importación temporal (roja)", pattern: LDDDD,
     regex: "^T[0-9]{4}$", verified: false, vehicle_types: [car, motorcycle, bus, truck],
     source: "Prensa / Wikipedia; sin fuente oficial"}
```

Notas del catálogo:
- `co_motocarro` y los no verificados admiten los cuatro tipos porque COCO no tiene clase motocarro y
  no hay fuente sobre el vehículo que arrastra el remolque; la coherencia tipo↔formato no aplica.
- Policía/Fuerzas Militares y maquinaria no se incluyen: formato NO VERIFICADO (lecturas con esas
  formas quedan `UNRECOGNIZED_FORMAT` → revisión).

### Validaciones de configuración (además de tipos)

| Campo | Regla |
|---|---|
| `version` | `== 1` |
| `input.allowed_extensions` | cada una empieza por `.` y es minúscula; no vacía |
| `input.max_file_size_mb` | 1..102400 |
| `models.*.score_threshold` | [0, 1] |
| `models.*.input_size` | múltiplo de 32 entre 32 y 1280 |
| `models.plate_detector.backend` | `open_image_models` o `yolo` |
| `tracker.cmc_method` | `sparseOptFlow`, `orb`, `sift`, `ecc` |
| `tracker.*threshold*` | [0, 1]; `lost_track_buffer >= 0`; `minimum_consecutive_frames >= 1`; `cmc_downscale >= 1` |
| `default_profile` | existe en `profiles` |
| `profiles.*` | `target_fps` (0, 120]; enteros ≥ 1; umbrales [0, 1]; `min_sharpness >= 0`; `vehicle_crop_margin` [0, 1]; `mode` ∈ {`estatico`, `movil`}; si `mode` es `movil`, `camera_motion_compensation` debe ser `true` (spec 056); `near_min_width_frac` [0, 0.2]; `max_plate_vehicle_ratio` (0, 1]; `roi` 0 ≤ x1 < x2 ≤ 1 y 0 ≤ y1 < y2 ≤ 1 (spec 057); `early_stop` bool (spec 060); `dedup_window_ms` [0, 600000] (spec 061) |
| `consolidation.confusions` | pares `[letra A-Z, dígito 0-9]`, sin letras ni dígitos repetidos |
| `retention` | `1 <= crops_days <= records_days <= 3650`; `1 <= training_days <= 3650` |
| `plate_formats` | ≥ 1; `format_id` únicos; `regex` compila; `pattern` `^[LD]{1,10}$` |

## 5. Manifiesto de modelos — `config/models.yaml`

```yaml
version: 1
models:
  - {model_id: oim-yolo-v9-t-384-plates, filename: yolo-v9-t-384-license-plates-end2end.onnx,
     url: "https://github.com/ankandrew/open-image-models/releases/download/assets/yolo-v9-t-384-license-plates-end2end.onnx",
     sha256: 888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8, size_bytes: 7771218,
     license: "MIT (repositorio; licencia específica de pesos NO VERIFICADA)", source: open-image-models 0.6.0}
  - {model_id: fpo-cct-xs-v2-global, filename: cct_xs_v2_global.onnx,
     url: "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global.onnx",
     sha256: 8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44, size_bytes: 3344292,
     license: MIT, source: fast-plate-ocr 1.1.0}
  - {model_id: fpo-cct-xs-v2-global-config, filename: cct_xs_v2_global_plate_config.yaml,
     url: "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global_plate_config.yaml",
     sha256: 0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6, size_bytes: 1725,
     license: MIT, source: fast-plate-ocr 1.1.0}
  - {model_id: yolo26n-coco, filename: yolo26n-coco.onnx, url: "https://github.com/sergiopon/lectorPlacas/releases/download/models-v1/yolo26n-coco.onnx",
     sha256: 28d570970b867a53a4c5c7787db0c22372882bbbcc1d68d3c0a657ea97cf7b64, size_bytes: 9942097,
     license: AGPL-3.0, source: "exportado localmente desde yolo26n.pt (spec 030)"}
  - {model_id: yolo26n-plates, filename: yolo26n-plates.onnx, url: "https://github.com/sergiopon/lectorPlacas/releases/download/models-v1/yolo26n-plates.onnx",
     sha256: 8676a19b5388ce852b0a71fcb6ced841efce33bbc2fa638fbf2a76484f4ea770, size_bytes: 9804866,
     license: AGPL-3.0, source: "YOLO26n fine-tuneado con placas colombianas (spec 030)"}
  - {model_id: fpo-cct-xs-v2-colombia, filename: fpo-cct-xs-v2-colombia.onnx, url: "https://github.com/sergiopon/lectorPlacas/releases/download/models-v1/fpo-cct-xs-v2-colombia.onnx",
     sha256: 2a057dd8922cd5267fe6fe66c3d09dee6119bacc8929b36a26c06c70f2a327e8, size_bytes: 3080105,
     license: MIT, source: "cct-xs-v2-global fine-tuneado con placas colombianas (spec 032; ADR-014 v1, PROVISIONAL: no cumple M-04: CER 0,0373 > 0,03 y cota IC 95 % 0,0667 > 0,05 sobre mix_v1/test, n=215)"}
```

- `sha256: PENDIENTE_EXPORT` es el único valor no hexadecimal admitido y significa "aún no exportado":
  `verified_path` lanza `ModelIntegrityError("modelo no exportado")`. El script de exportación
  (spec 030) imprime el SHA-256 y el tamaño que el operador copia aquí.
- Validación: `model_id` `^[a-z0-9][a-z0-9-]{1,63}$` único; `filename` sin `/` ni `..`;
  `url` nulo o empieza por `https://github.com/`; `sha256` `^[0-9a-f]{64}$` o `PENDIENTE_EXPORT`;
  `size_bytes >= 0`.
- Ubicación del archivo: `models/<model_id>/<filename>`.
