# Índice de specs

Orden de implementación = orden numérico. Cada spec se envía a DeepSeek junto con `CONTEXT.md`.
Estados: **Lista** (redactada, pendiente de implementar) · **Por redactar** · **Implementada** · **Aprobada**.

| # | Spec | Depende de | Estado |
|---|---|---|---|
| 000 | [Setup](000-setup.md) | — | Implementada |
| 001 | [Dominio: entidades y errores](001-dominio-entidades-errores.md) | 000 | Implementada |
| 002 | [Dominio: catálogo de formatos](002-dominio-catalogo-formatos.md) | 001 | Lista |
| 003 | [Dominio: corrección posicional](003-dominio-correccion-posicional.md) | 001 | Lista |
| 004 | [Dominio: consolidación y mask_plate](004-dominio-consolidacion.md) | 001, 002, 003 | Lista |
| 005 | [Aplicación: puertos, reloj, fakes](005-aplicacion-puertos.md) | 001 | Lista |
| 006 | [Configuración](006-configuracion.md) | 001–004 | Lista |
| 007 | [Rutas seguras y validación de entrada](007-validacion-entradas-rutas.md) | 001 | Lista |
| 008 | [Cifrado y clave maestra](008-cifrado-y-claves.md) | 001, 005 | Lista |
| 009 | [Muestreo de frames](009-muestreo-frames.md) | 001, 005 | Lista |
| 010 | [Fuente de video PyAV](010-fuente-video-pyav.md) | 001, 005 | Lista |
| 011 | [Sesión ONNX y letterbox](011-onnx-sesion-letterbox.md) | 001, 005 | Lista |
| 012 | [YOLO end2end ONNX](012-yolo-end2end-onnx.md) | 011 | Lista |
| 013 | [Detector de vehículos](013-detector-vehiculos.md) | 012 | Lista |
| 014 | [Detector de placas open-image-models](014-detector-placas-oim.md) | 011 | Lista |
| 015 | [Detector de placas YOLO propio](015-detector-placas-yolo.md) | 012 | Lista |
| 016 | [Tracker BoT-SORT](016-tracker-botsort.md) | 001, 005 | Lista |
| 017 | [OCR fast-plate-ocr](017-ocr-fast-plate-ocr.md) | 011 | Lista |
| 018 | [Nitidez de recortes](018-calidad-imagen.md) | 005 | Lista |
| 019 | [Registro de modelos y guardia de red](019-registro-modelos-red.md) | 001, 005, 007 | Lista |
| 020 | [Repositorio SQLCipher](020-repositorio-sqlcipher.md) | 001, 005, 008 | Lista |
| 021 | [Almacén de recortes cifrado](021-almacen-recortes-cifrado.md) | 005, 007, 008 | Lista |
| 022 | [Logging enmascarado](022-logging-enmascarado.md) | 004, 007 | Lista |
| 023 | [Registro de tracks e image_ops](023-registro-tracks.md) | 001, 005 | Lista |
| 024 | [Orquestador ProcessVideo](024-orquestador-procesar-video.md) | 004, 005, 009, 023 | Lista |
| 025 | [Purga por retención](025-retencion-purga.md) | 005 | Lista |
| 026 | [Exportación CSV](026-exportacion-csv.md) | 005, 007 | Lista |
| 027 | [Revisión humana](027-revision-humana.md) | 005 | Lista |
| 028 | [CLI y composición](028-cli-composicion.md) | 006–027 | Lista |
| 029 | [Evaluación](029-evaluacion.md) | 028 | Lista |
| 030 | [Entrenamiento del detector y export ONNX](030-entrenamiento-detector.md) | 000 (031 para entrenar placas) | Lista |
| 031 | [Herramientas de dataset](031-herramientas-dataset.md) | 002, 007, 023, 028 | Lista |
| 032 | [Entrenamiento del OCR (fine-tuning)](032-entrenamiento-ocr.md) | 000 (031 para entrenar con datos reales) | Lista |
| 033 | [Generador de placas sintéticas](033-generador-sintetico.md) | 032 | Lista |

Nota: para probar el pipeline completo (028, test gpu) hace falta antes la spec 030 (exportar `yolo26n-coco.onnx`).

Pendiente de decisión del usuario: exportar recortes propios (descifrados) para entrenar — choca con SEG-07 y SEG-03 (ver docs/04-evaluacion.md §5.2).

## Correcciones de specs (hechas por el orquestador)

| Fecha | Spec | Cambio | Motivo |
|---|---|---|---|
| 2026-09-26 | 000 | `extend-exclude` añade `"*.md"`; `per-file-ignores` de tests añade `"S603"` | ruff formateaba bloques de código de specs/docs (solo lectura); el test de GPU usa `subprocess` |
| 2026-09-26 | ARQUITECTURA §6 | Excepción al límite de 300 líneas para `entities.py` y `ports.py` | Su contenido lo fija el contrato; partirlos cambiaría imports de todas las specs |
