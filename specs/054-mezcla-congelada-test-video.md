# 054 - Entrenamiento OCR: mezcla que hereda el reparto congelado y split `test_video`

## Objetivo
Reentrenar el OCR con los recortes reales de video revisados (`lector dataset export-reviewed`, spec 035) **sin tocar
el `test` congelado de `mix_v1`** (ADR-014) y midiendo aparte el dominio que importa: el video.

Hoy no se puede. `mix_dataset` reparte ordenando los componentes por hash y tomando los primeros `round(n × 0,2)` para
test. Si se añade una fuente real a la misma mezcla, cambian `n` y el orden, y parte del `test` de `mix_v1` pasa a train:
medir después sobre ese test daría un CER falso (fuga). Además, `evaluate_ocr` solo acepta un split llamado `test` y
siempre compara con el modelo base global, así que no puede comparar `colombia_v2` con `colombia_v1` en video.

Contexto (docs/07 §1 y Fase 0): CER real en video 0,1615 (92 lecturas revisadas), frente a 0,0373 en `mix_v1/test`.

## Depende de
035, 039.

## Archivos rectores aplicables
- docs/adr/ADR-014-receta-entrenamiento-ocr.md (test congelado, niveles de aceptación).
- docs/04-evaluacion.md §5.3 (M-04). No cambia ningún criterio.
- reglas-seguridad.md SEG-04 (directorios 0700 y archivos 0600), SEG-05 (sin textos de placa en consola, reportes ni
  manifiesto). Los datos son reales y locales: nada sale del equipo.
- CLAUDE.md, sección OCR (se ejecuta desde `training/ocr`).

## Archivos a crear/modificar
- `training/ocr/ocr_training/mix_frozen.py` (nuevo)
- `training/ocr/ocr_training/mix_dataset.py`
- `training/ocr/ocr_training/evaluate_ocr.py`
- `training/ocr/tests/test_mix_frozen.py` (nuevo)
- `training/ocr/tests/test_evaluate_ocr.py`

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
- `mix_dataset.build_mix(...)` gana el parámetro con nombre `frozen_dir: Path | None = None`, al final. Con `None` el
  comportamiento es **idéntico** al actual (manifiesto `version` 1, tres splits); los tests existentes pasan sin cambios.
- CLI de `mix_dataset`: opción nueva `--frozen-from` (Path, opcional, relativa a `DATASETS_DIR`).
- Constante nueva `TEST_VIDEO_SPLIT = "test_video"`. `mix_split.SPLITS` no cambia.
- `mix_frozen.py` (contenido público mínimo; los nombres privados los decide el implementador):
  - `load_frozen(mix_dir: Path) -> FrozenMix`: `FrozenMix` es un dataclass inmutable con las filas reales por split y los
    nombres de sus fuentes reales.
  - `assign_new_components(...)`: reparte los componentes de las fuentes nuevas (ver Comportamiento, 3).
- `evaluate_ocr`:
  - `read_split` acepta un split llamado `test` **o** `test_video`.
  - CLI: opción nueva `--baseline` (Path, opcional, relativa a `TRAINING_DIR`, p. ej.
    `runs/colombia_v1/<fecha>/best.onnx`).

## Comportamiento esperado

### 1. `load_frozen(mix_dir)`
- `mix_dir` debe estar dentro de `DATASETS_DIR`, ser un directorio y contener `manifest.json` (es una salida de
  `mix_dataset`) y `train`, `val` y `test` con su `annotations.csv`. Si no → `TrainingError`.
- Por split se leen solo las filas **reales**, identificadas porque el nombre del archivo empieza por `real_` (así las
  nombra `mix_dataset._place`). Las `syn_` se ignoran. En `val` y `test` se lee además `groups.csv` y cada fila conserva
  su `group_id`. La ruta de la imagen se guarda resuelta y el orden de archivo se conserva.
- Mapa texto → split: si un mismo texto aparece en dos splits distintos → `TrainingError("mezcla congelada inconsistente")`.
- `real_sources` = la lista `real_sources` del manifiesto.

### 2. Validaciones de `build_mix` con `frozen_dir`
Van antes de crear nada, además de las actuales:
- Si alguna fuente de `--real` tiene el mismo nombre que una de `real_sources` de la mezcla congelada →
  `TrainingError("fuente ya incluida en la mezcla congelada: <nombre>")`. Así se evita duplicar `ocr_colombia`.
- `test_fraction` y `val_fraction` se validan como hoy y se aplican solo a las fuentes nuevas.

### 3. Reparto de las fuentes nuevas
- `nuevos = load_real(d)` para cada `--real`, concatenados; `comps = components(nuevos)` (mismo criterio que hoy: texto
  **o** imagen de origen).
- **Anclaje:** un componente cuyo algún texto está en el mapa congelado va al split más restrictivo en que aparezca,
  con el orden `test` > `val` > `train`. Los anclados a `test` van a `test_video`, nunca a `test`: el test congelado
  no cambia.
- **Libres:** los componentes no anclados se reparten con `split_components(libres, val_fraction, test_fraction, seed)`
  (estratificado y determinista, como hoy). Su parte `test` va a `test_video`. Si esa función lanza (partición vacía),
  el error se propaga: hacen falta más datos nuevos.

### 4. Composición de la salida con `frozen_dir`
Cuatro splits:
- `test`: **copia exacta** del `test` congelado. `annotations.csv`, `groups.csv` e `images/` idénticos byte a byte
  (se copian los archivos, no se regeneran nombres).
- `val`: primero las filas reales congeladas de `val`, en su orden y con su `group_id`; luego los componentes nuevos de
  `val` (anclados y después libres), con `group_id` que continúa la numeración (`g<k:05d>`, `k` = máximo congelado + 1…).
  Nombres de imagen regenerados con `_place`.
- `train`: filas reales congeladas de `train`, después los componentes nuevos de `train` y al final los sintéticos
  elegidos.
- `test_video`: componentes anclados a test y después los libres de test, con `groups.csv` numerado desde `g00000`.
- Sintéticos: `select_synthetic` con `real_train` = reales congelados de train más los nuevos de train, y textos
  excluidos = los de `val`, `test` y `test_video`. Los sintéticos de la mezcla congelada no se reutilizan.
- Permisos, escritura atómica (se borra la salida si algo falla) y `validate_annotations` de los cuatro CSV: como hoy.
- Manifiesto con `"version": 2`, `"frozen_from": <nombre de la mezcla congelada>`, `"real_sources"` = solo las fuentes
  nuevas, y `"splits"` con las cuatro claves y los mismos conteos que hoy. Nunca lleva textos de placa.
- CLI: imprime una línea por split, incluida `test_video`, con el mismo formato actual.

### 5. `evaluate_ocr`
- `read_split`: `csv_path.parent.name` debe ser `test` o `test_video`; si no →
  `TrainingError("la evaluación se mide en test o test_video")`. El resto de validaciones no cambia.
- `--baseline`:
  - Si se indica: debe existir dentro de `TRAINING_DIR` y pasar `check_ocr_onnx`. Se usa en lugar de `BASELINE_ONNX`.
    El reporte guarda `baseline_model_id = "custom"`, `baseline_path` (relativo a `TRAINING_DIR`) y `baseline_sha256`.
  - Sin `--baseline`: exactamente el comportamiento actual (base global verificado por hash).
- El reporte añade `"split": <nombre del split evaluado>`. `decide` no cambia: con un `test_video` de menos de
  `MIN_TEST_SAMPLES` recortes la decisión será RECHAZAR por "muestra insuficiente", y eso es lo correcto. Sobre
  `test_video` la cifra es informativa (comparar CER e IC); la aceptación del modelo sigue midiéndose en `mix_v1/test`
  (ADR-014).

### 6. Flujo del operador (se documenta aquí; no es código)
Desde `training/ocr`:
1. `mix_dataset --frozen-from mix_v1 --real own/<export> --synthetic syn_v1 --output mix_v2 --seed 0`.
2. `train --train mix_v2/train/annotations.csv --val mix_v2/val/annotations.csv ... --name colombia_v2`.
3. Aceptación (ADR-014): `evaluate_ocr --crops mix_v2/test/annotations.csv --candidate runs/colombia_v2/<fecha>/best.onnx`.
   Es el mismo test que `mix_v1`.
4. Video: `evaluate_ocr --crops mix_v2/test_video/annotations.csv --candidate runs/colombia_v2/<fecha>/best.onnx
   --baseline runs/colombia_v1/<fecha>/best.onnx`. `train.py` sobrescribe `models/fpo-cct-xs-v2-colombia/`, así que la
   referencia v1 se toma de `runs/`.

## Casos borde y manejo de errores
- Un recorte nuevo con el mismo texto que uno del test congelado va a `test_video`, no a train (sin fuga).
- `--frozen-from` apuntando a algo que no es una mezcla, o con un split sin `annotations.csv` → `TrainingError`.
- Mismos argumentos y `seed` → misma salida, byte a byte, en los cuatro splits.
- Ningún mensaje, log ni manifiesto contiene textos de placa. Los mensajes de error pueden llevar nombres de fuente o
  de ruta, pero no textos.

## Tests de aceptación
En `training/ocr/tests/`, con el patrón de los tests actuales de `test_mix_dataset.py`: `DATASETS_DIR` sustituido con
`monkeypatch` por un directorio en `tmp_path`, imágenes sintéticas pequeñas escritas con OpenCV y textos sintéticos
(`ABC123`, `XYZ98K`…). La mezcla congelada de cada test se construye con `build_mix` sin `frozen_dir`.

### `test_mix_frozen.py` (nuevo)
1. `test_frozen_test_is_copied_byte_for_byte`: con `frozen_dir`, los tres archivos de `test` (`annotations.csv`,
   `groups.csv` y cada imagen) son idénticos a los de la mezcla congelada.
2. `test_frozen_rows_keep_their_split`: toda fila real congelada de train y de val aparece en el mismo split de la salida
   (se compara el contenido de las imágenes o el texto, no el nombre).
3. `test_new_sample_sharing_test_text_goes_to_test_video`: un recorte nuevo con el texto de una placa del test congelado
   termina en `test_video`, y ningún split de la salida tiene ese texto en train.
4. `test_anchor_precedence_is_test_then_val_then_train`: un componente nuevo que une (por imagen de origen) un texto del
   val congelado y otro del train congelado va a `val`.
5. `test_free_components_split_with_test_to_test_video`: con suficientes componentes nuevos no anclados, hay filas
   nuevas en train, val y `test_video`, y `test` sigue idéntico al congelado.
6. `test_synthetics_exclude_eval_texts`: ningún sintético de train comparte texto con `val`, `test` ni `test_video`.
7. `test_repeated_source_is_rejected`: pasar como `--real` una fuente con el mismo nombre que una de la mezcla congelada
   lanza `TrainingError` y no crea la salida.
8. `test_invalid_frozen_dir_is_rejected`: un directorio sin `manifest.json` lanza `TrainingError`.
9. `test_manifest_version_2_without_plate_text`: el manifiesto tiene `version == 2`, `frozen_from`, las cuatro claves de
   `splits` y no contiene ningún texto de placa de los datos de prueba.
10. `test_frozen_mix_is_deterministic`: dos ejecuciones con la misma semilla dan salidas idénticas byte a byte.
11. `test_main_prints_test_video_line`: la CLI con `--frozen-from` imprime la línea de `test_video` y ningún texto de placa.

Los tests existentes de `test_mix_dataset.py` pasan sin cambios.

### `test_evaluate_ocr.py`
12. `test_read_split_accepts_test_video`: un `test_video/annotations.csv` con `groups.csv` se lee igual que `test`; un
    split llamado `val` lanza `TrainingError`.
13. `test_custom_baseline_is_used_and_reported`: con un predictor falso inyectado (como en los tests actuales), la
    evaluación usa el baseline indicado y el reporte lleva `baseline_model_id == "custom"` y el `split` evaluado.

`test_read_split_errors` (split `val`, sintéticos y sin `groups.csv`) y los demás casos existentes pasan sin cambios.

## Fuera de alcance
- Cambiar `train.py`, el generador sintético o `chars_to_ocr`.
- Registrar `colombia_v2` en `config/models.yaml` (lo hace el operador si se acepta).
- Cambiar los umbrales de M-04 o de `decide`.

## Definition of Done
- Desde `training/ocr`: `uv run pytest` pasa (mismas compuertas que la spec 039).
- Ningún módulo importa `lector_placas`; `git status` no muestra `datasets/` ni `runs/`.
- Módulos ≤ 300 líneas (`wc -l`); `mix_dataset.py` delega en `mix_frozen.py` lo necesario para no pasarse.
- Solo cambian los archivos listados.
