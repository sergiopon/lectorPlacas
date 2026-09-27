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

Nota: para probar el pipeline completo (028, test gpu) hace falta antes la spec 030 (exportar `yolo26n-coco.onnx`).

Decisión del usuario (2026-09-26): exportar lecturas revisadas con retención propia (180 días) → spec 035; excepción documentada en SEG-07/SEG-03 y ADR-005.
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
