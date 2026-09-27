# Índice de specs

Orden de implementación = orden numérico. Cada spec se envía a DeepSeek junto con `CONTEXT.md`.
Estados: **Lista** (redactada, pendiente de implementar) · **Por redactar** · **Implementada** · **Aprobada**.

| # | Spec | Depende de | Estado |
|---|---|---|---|
| 000 | [Setup](000-setup.md) | — | Implementada |
| 001 | [Dominio: entidades y errores](001-dominio-entidades-errores.md) | 000 | Implementada |
| 002 | [Dominio: catálogo de formatos](002-dominio-catalogo-formatos.md) | 001 | Implementada |
| 003 | [Dominio: corrección posicional](003-dominio-correccion-posicional.md) | 001 | Implementada |
| 004 | [Dominio: consolidación y mask_plate](004-dominio-consolidacion.md) | 001, 002, 003 | Implementada |
| 005 | [Aplicación: puertos, reloj, fakes](005-aplicacion-puertos.md) | 001 | Implementada |
| 006 | [Configuración](006-configuracion.md) | 001–004 | Implementada |
| 007 | [Rutas seguras y validación de entrada](007-validacion-entradas-rutas.md) | 001 | Implementada |
| 008 | [Cifrado y clave maestra](008-cifrado-y-claves.md) | 001, 005 | Implementada |
| 009 | [Muestreo de frames](009-muestreo-frames.md) | 001, 005 | Implementada |
| 010 | [Fuente de video PyAV](010-fuente-video-pyav.md) | 001, 005 | Implementada |
| 011 | [Sesión ONNX y letterbox](011-onnx-sesion-letterbox.md) | 001, 005 | Implementada |
| 012 | [YOLO end2end ONNX](012-yolo-end2end-onnx.md) | 011 | Implementada |
| 013 | [Detector de vehículos](013-detector-vehiculos.md) | 012 | Implementada |
| 014 | [Detector de placas open-image-models](014-detector-placas-oim.md) | 011 | Implementada |
| 015 | [Detector de placas YOLO propio](015-detector-placas-yolo.md) | 012, 013 | Implementada |
| 016 | [Tracker BoT-SORT](016-tracker-botsort.md) | 001, 005 | Implementada |
| 017 | [OCR fast-plate-ocr](017-ocr-fast-plate-ocr.md) | 011 | Implementada |
| 018 | [Nitidez de recortes](018-calidad-imagen.md) | 005 | Implementada |
| 019 | [Registro de modelos y guardia de red](019-registro-modelos-red.md) | 001, 005, 007 | Implementada |
| 020 | [Repositorio SQLCipher](020-repositorio-sqlcipher.md) | 001, 005, 008 | Implementada |
| 021 | [Almacén de recortes cifrado](021-almacen-recortes-cifrado.md) | 005, 007, 008 | Implementada |
| 022 | [Logging enmascarado](022-logging-enmascarado.md) | 004, 007 | Implementada |
| 023 | [Registro de tracks e image_ops](023-registro-tracks.md) | 001, 005 | Implementada |
| 024 | [Orquestador ProcessVideo](024-orquestador-procesar-video.md) | 004, 005, 009, 023 | Implementada |
| 025 | [Purga por retención](025-retencion-purga.md) | 005 | Implementada |
| 026 | [Exportación CSV](026-exportacion-csv.md) | 005, 007 | Implementada |
| 027 | [Revisión humana](027-revision-humana.md) | 005 | Implementada |
| 028 | [CLI y composición](028-cli-composicion.md) | 006–027 | Implementada |
| 029 | [Evaluación](029-evaluacion.md) | 028 | Implementada |
| 030 | [Entrenamiento del detector y export ONNX](030-entrenamiento-detector.md) | 000 (031 para entrenar placas) | Implementada |
| 031 | [Herramientas de dataset](031-herramientas-dataset.md) | 002, 007, 023, 028 | Implementada |
| 032 | [Entrenamiento del OCR (fine-tuning)](032-entrenamiento-ocr.md) | 000 (031 para entrenar con datos reales) | Implementada |
| 033 | [Generador de placas sintéticas](033-generador-sintetico.md) | 032 | Implementada |
| 034 | [Revisión: interfaz en la ventana](034-revision-ui-ventana.md) | 027 | Implementada |
| 035 | [Exportar lecturas revisadas para reentrenar el OCR](035-exportar-revisados.md) | 006, 021, 025, 026, 028, 031 | Implementada |
| 036 | [Descarga automática de datasets (Roboflow) y preparación](036-descarga-datasets.md) | 007, 019, 028, 031 | Implementada |
| 037 | [Métrica del detector de placas sobre dataset](037-evaluar-detector.md) | 014, 015, 029, 031 | Implementada |
| 038 | [Auditoría de confirmadas y métricas desde la revisión](038-metricas-revision.md) | 027, 029, 034 | Implementada |
| 039 | [Mezcla real + sintético y aceptación del OCR](039-mezcla-dataset-ocr.md) | 031, 032, 033 | Implementada |
| 040 | [Progreso y cancelación de `ProcessVideo`](040-progreso-cancelacion.md) | 024 | Implementada |
| 041 | [Búsqueda de avistamientos y corridas (`SightingBrowser`)](041-busqueda-avistamientos.md) | 005, 020 | Implementada |
| 042 | [GUI: dependencia, arranque, sesión y ventana](042-gui-base.md) | 028, 041 | Implementada |
| 043 | [GUI: pestaña Procesar](043-gui-procesar.md) | 040, 041, 042 | Implementada |
| 044 | [GUI: avistamientos y revisión en diálogo Qt](044-gui-avistamientos-revision.md) | 038, 041, 042, 043 | Lista |
| 045 | [GUI: exportar, retención y métricas](045-gui-exportar-retencion-metricas.md) | 025, 026, 038, 042–044 | Lista |

Nota: para probar el pipeline completo (028, test gpu) hace falta antes la spec 030 (exportar `yolo26n-coco.onnx`).

Decisión del usuario (2026-09-26): exportar lecturas revisadas con retención propia (180 días) → spec 035; excepción documentada en SEG-07/SEG-03 y ADR-005.
Decisión del usuario (2026-09-27): GUI de escritorio PySide6 (ADR-015, RF-36) → specs 040–045. Todo el código lo implementa DeepSeek; desde estas specs los tests de aceptación se describen en prosa (Claude no escribe código, tampoco en specs), así que la compuerta de "tests intactos por AST" se sustituye por la revisión de que existan los casos nombrados con el comportamiento descrito.
Decisión del usuario (2026-09-26): métricas con datasets en vez de ground truth manual → spec 036 (descarga por API REST de Roboflow; excepción de red en SEG-20/SEG-21 y ADR-012; clave solo en `ROBOFLOW_API_KEY`).

## Correcciones de specs (hechas por el orquestador)

| Fecha | Spec | Cambio | Motivo |
|---|---|---|---|
| 2026-09-26 | 000 | `extend-exclude` añade `"*.md"`; `per-file-ignores` de tests añade `"S603"` | ruff formateaba bloques de código de specs/docs (solo lectura); el test de GPU usa `subprocess` |
| 2026-09-26 | ARQUITECTURA §6 | Excepción al límite de 300 líneas para `entities.py` y `ports.py` | Su contenido lo fija el contrato; partirlos cambiaría imports de todas las specs |
| 2026-09-26 | docs/03 §5 y 019 | Hash real de `yolo26n-coco.onnx` (exportado en la spec 030) en el manifiesto; el test de 019 comprueba `yolo26n-plates` como pendiente | Registro del modelo exportado (paso del operador) |
| 2026-09-26 | 000 (pyproject) | `per-file-ignores` de tests añade `"S108"` | Los tests literales de 006 y 022 usan rutas `/tmp` como valores de prueba |
| 2026-09-26 | ARQUITECTURA §6 | La excepción de tamaño incluye `infrastructure/config.py` | La spec 006 fija todos los modelos de configuración en ese módulo |
| 2026-09-26 | README (índice) | 015 depende también de 013 | Importa `YoloPredictor` definido en la 013 |
| 2026-09-26 | 029 | El test literal `test_missing_nvidia_smi` combina los `with` en una sola sentencia | El anidado de `with` del literal dispara SIM117 de ruff, que está activo en el proyecto |
| 2026-09-26 | 032 | Paso 5.6: la exportación ONNX se hace en un subproceso con `KERAS_BACKEND=tensorflow` y `CUDA_VISIBLE_DEVICES=""` sobre una copia del `.keras` sin `compile_config`; nota en ADR-011 y ADR-003 | `torch.onnx` falla con `SymbolicValueError` en el kernel de `PatchExtractor` con `--dynamic-batch`; el `compile_config` del modelo torch referencia `keras.src.backend.torch.optimizers.torch_adamw` y aborta el proceso al cargarse con TensorFlow; con la GPU visible, grappler de TF falla |
| 2026-09-26 | 028, 029, SEG-20, ADR-012 | `main` lee la clave maestra (`args.keys`) antes de `block_network()`; los comandos reutilizan el proveedor | La guardia bloquea el socket Unix de D-Bus y el keyring fallaba (`KeyUnavailableError`) en todo comando con BD |
| 2026-09-26 | 027 → 034 | La UI de revisión pasa a interactuar solo dentro de la ventana (bucle de `waitKey`, campo de edición, diseño nuevo); spec 034 reemplaza el adaptador de 027 | Con Qt5/XWayland la ventana no se dibujaba o quedaba "no responde" mientras `input()` bloqueaba la terminal |
| 2026-09-26 | SEG-03, SEG-07, ADR-005, docs/02-04, CONTEXT | Excepción controlada para exportar lecturas revisadas y `retention.training_days` | Decisión del usuario: reentrenar el OCR con sus lecturas confirmadas/corregidas |
| 2026-09-26 | 036 | `ocr_placas_colombia` apunta a un fork propio (`sergio-ponce-asprilla/ocr-placas-colombia-etll5-lwpkc`, versión 1 sin aumentos); `placas_colombianas` se elimina del registro; `latest_version` distingue lista vacía (`sin versiones generadas: <ws>/<project>`) de formato inesperado; forma de `id` verificada con la API real; tests del registro ajustados (sin depender de una entrada `auto` del YAML) | Los originales tenían 0 versiones y Roboflow no exporta sin versión generada. `placas_colombianas` tampoco sirve: su `data.yaml` trae 50 clases con texto del README como nombres (las clases del proyecto están corruptas), así que `plate_classes: auto` falla y no se puede saber qué es cada clase |
| 2026-09-26 | 031, 036 | `parse_label_file` acepta líneas de polígono (`clase x1 y1 ... xn yn`, `n >= 3`) y las convierte en su caja envolvente; `dataset prepare` borra la salida parcial de `merge_detection`/`chars_to_ocr` si fallan y no toma por "ya preparada" una carpeta vacía | Roboflow exporta `yolov8` con polígonos en proyectos de segmentación (`usco`, `ocr_placas_colombia`): `etiqueta inválida` detenía `prepare`, y la carpeta `merged` parcial hacía que el reintento dijera "ya preparado" |
| 2026-09-27 | 036, docs/04 | `placas_motos_carros`: `plate_classes` pasa de `Placas` a `Proyecto_Placas - vdataset reimerjsuarezs-workspace` | Verificado en las etiquetas descargadas: la clase 1 (nombre tomado del README de Roboflow) tiene 1 239 cajas de placa y `Placas` (clase 0) solo 2; con la clase equivocada 1 027 de 1 029 imágenes quedaban como negativas sin caja |
| 2026-09-27 | 031, 036, docs/04 | `usco` se elimina del registro del detector; `chars_to_ocr` divide `train` por grupo de imagen de origen (sufijo `.rf.<hash>`, ~10 % de grupos a val por SHA-256) cuando la fuente no trae `valid`/`test`, y descarta de val los textos ya presentes en train; tests del registro y del CLI ajustados | Decisión delegada a Opus 5.5 con datos verificados: en `usco` el 100 % de las imágenes tienen una caja >80 % de la imagen (recortes de placa) y sesgaría el detector e inflaría la validación; el export del OCR solo trae `train` (926 imágenes de 686 orígenes, con copias que el dHash no detecta) y una división aleatoria de Roboflow filtraría copias entre train y val |
| 2026-09-27 | 019, docs/03 §5 | Hash y tamaño reales de `yolo26n-plates.onnx` en el manifiesto; el test de 019 comprueba `fpo-cct-xs-v2-colombia` como pendiente | Registro del detector de placas entrenado (spec 030, paso del operador) |
| 2026-09-27 | docs/04 §5.3, ARQUITECTURA §8, docs/05 | Nota de la primera iteración del OCR (ADR-014: 1 106 de train, 88 val + 215 test reales, partición por componente); ADR-014 en el índice; 039 asignada | Datos reales verificados: 856 recortes / 492 componentes, 7,2 % motos; la val de 50 recortes de `chars-to-ocr` no permite medir M-04 |
| 2026-09-27 | 039 | `write_report` crea `reports_dir` con `mode=0o700` | SEG-04: el directorio de reportes debe ser 0700 (hallazgo de la revisión) |
| 2026-09-27 | ADR-014, docs/04 §5.3 | Decisiones aprobadas: primera iteración por debajo de §5.3, 30 % de vehículos reales a val/test, test de `mix_v1` congelado y aceptación en dos niveles (aceptado / provisional que no cumple M-04 / rechazado) | Con ≈ 98 vehículos de test el IC 95 % puede fallar aunque el modelo supere al base; `evaluate_ocr` y la spec 039 no cambian |
| 2026-09-27 | 019, docs/03 §5 | Hash y tamaño reales de `fpo-cct-xs-v2-colombia.onnx` en el manifiesto (nivel PROVISIONAL, ADR-014); el test de 019 comprueba ese prefijo de hash en lugar de `PENDIENTE_EXPORT` (ya no quedan modelos pendientes) | Registro del OCR fine-tuneado (spec 032/039, paso del operador) |
| 2026-09-27 | config/lector.yaml | `models.ocr.model_id` pasa a `fpo-cct-xs-v2-colombia` (PROVISIONAL, ADR-014) | Mejora al modelo base en el `test` congelado (CER 0,0373 frente a 0,0536; exact-match 0,921 frente a 0,865; motos no empeoran); `lector evaluate-ocr` reproduce el CER de `evaluate_ocr` exactamente |
| 2026-09-27 | 011, 028 | `ensure_cuda_libraries` (pública en `onnx_session.py`) se llama también en `build_reader` y en `build_plate_detector` (backend `open_image_models`) | `evaluate-ocr` y `evaluate-detector` no pasaban por `create_session` y caían a CPU por `libcublasLt.so.13` no cargada; `process` funcionaba porque el detector de vehículos ya precargaba |
| 2026-09-27 | SEG-20, ADR-012, CONTEXT, docs/06 | `lector_placas/__init__.py` fija `ORT_DISABLE_TELEMETRY=1` antes de importar `onnxruntime`; el log de `strace` del nivel F se crea 0600 | El nivel F detectó 10 `connect` HTTPS (puerto 443, IPs de Microsoft) desde un hilo nativo de ONNX Runtime 1.30 (telemetría), que `block_network()` no ve. Con la variable puesta antes del import hay 0; puesta después del import o con `disable_telemetry_events()` siguen 6-8 (medido). Además `strace` creaba su log con 0644 y el chequeo de permisos fallaba |
| 2026-09-27 | 00-requisitos (RF-28, RF-36, §7), ARQUITECTURA §2/§4/§5/§6/§7, SEG-03/04/20, SEG-27, CONTEXT, docs/02 §1/§4/§5/§7 | Capa `gui` (segundo composition root; de `cli` solo importa `composition`), puertos `ProgressReporter` y `SightingBrowser`, `ProcessingCancelledError`, reglas de la GUI; nuevas specs 040–045 | ADR-015 aprobado (opción 2) tras la prueba de convivencia PySide6 + opencv-python |
