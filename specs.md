# Specs de lectorPlacas

Resumen de todas las specs: qué hace cada una, de cuáles depende y en qué estado está. Fecha: 2026-10-04.
Fuente de verdad del estado: `specs/README.md`. Las specs 056–064, 066–069, 073 y 074 están redactadas (2026-10-03); la 058 espera la aprobación del cambio de docs/04.
Las 065, 070–072 y 075 están bloqueadas: dependen de datos o artefactos que aún no existen. Diseño en `docs/09`.

Estados: **Implementada** (integrada en `main`) · **En implementación** (rama y worktree activos) · **Redactada**
(spec lista, sin implementar) · **Por redactar** (solo existe en el plan).

## Resumen

| Estado | Specs |
|---|---|
| Implementada | 000–057, 059–064, 066–071, 074, 076 (73 specs; 059–064, 066–071, 074 y 076 el 2026-10-04) |
| Redactada (lista para implementar) | 072, 073 (2) |
| Redactada, bloqueada | 058 (aprobación del cambio de M-02/M-03 en docs/04) |
| Bloqueada, sin redactar | 065 (normativa de placas), 070–072 (exportación de Figma Make), 075 (frontend e imágenes base) |

Cada spec se implementa en su rama `feature/NNN-*` y se integra con `merge --no-ff`. El orden numérico es el orden de
implementación; una spec no se empieza hasta que sus dependencias están integradas.

---

## 1. Base: dominio, aplicación y adaptadores (000–029)

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 000 | Setup: proyecto uv, Python 3.13, ruff, mypy strict, pytest, pre-commit | — | Implementada |
| 001 | Dominio: entidades y errores | 000 | Implementada |
| 002 | Dominio: catálogo de formatos de placa colombianos | 001 | Implementada |
| 003 | Dominio: corrección posicional (0↔O, 1↔I, 8↔B, 5↔S) | 001 | Implementada |
| 004 | Dominio: consolidación por voto y `mask_plate` | 001, 002, 003 | Implementada |
| 005 | Aplicación: puertos (Protocols), reloj y fakes de test | 001 | Implementada |
| 006 | Configuración (YAML validado) | 001–004 | Implementada |
| 007 | Rutas seguras y validación de entrada | 001 | Implementada |
| 008 | Cifrado AES-GCM y clave maestra en el keyring | 001, 005 | Implementada |
| 009 | Muestreo de frames por tiempo | 001, 005 | Implementada |
| 010 | Fuente de video con PyAV (PTS, rotación) | 001, 005 | Implementada |
| 011 | Sesión ONNX Runtime y letterbox | 001, 005 | Implementada |
| 012 | YOLO end2end sobre ONNX | 011 | Implementada |
| 013 | Detector de vehículos | 012 | Implementada |
| 014 | Detector de placas con open-image-models | 011 | Implementada |
| 015 | Detector de placas con YOLO propio | 012, 013 | Implementada |
| 016 | Tracker BoT-SORT | 001, 005 | Implementada |
| 017 | OCR con fast-plate-ocr | 011 | Implementada |
| 018 | Nitidez de recortes (calidad de imagen) | 005 | Implementada |
| 019 | Registro de modelos con SHA-256 y guardia de red | 001, 005, 007 | Implementada |
| 020 | Repositorio SQLCipher | 001, 005, 008 | Implementada |
| 021 | Almacén de recortes cifrado | 005, 007, 008 | Implementada |
| 022 | Logging con enmascarado de placas | 004, 007 | Implementada |
| 023 | Registro de tracks e `image_ops` | 001, 005 | Implementada |
| 024 | Orquestador `ProcessVideo` | 004, 005, 009, 023 | Implementada |
| 025 | Purga por retención | 005 | Implementada |
| 026 | Exportación CSV | 005, 007 | Implementada |
| 027 | Revisión humana (primera versión) | 005 | Implementada |
| 028 | CLI y composition root | 006–027 | Implementada |
| 029 | Evaluación (métricas sobre video con ground truth) | 028 | Implementada |

## 2. Entrenamiento, datasets y revisión en CLI (030–039)

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 030 | Entrenamiento del detector y exportación a ONNX (`training/detector`) | 000 (031 para placas) | Implementada |
| 031 | Herramientas de dataset (fusión de detección, caracteres → OCR) | 002, 007, 023, 028 | Implementada |
| 032 | Entrenamiento (fine-tuning) del OCR (`training/ocr`) | 000 (031 para datos reales) | Implementada |
| 033 | Generador de placas sintéticas | 032 | Implementada |
| 034 | Revisión: interfaz dentro de la ventana OpenCV (reemplaza el adaptador de 027) | 027 | Implementada |
| 035 | `dataset export-reviewed`: exporta lecturas revisadas para reentrenar el OCR, con retención propia | 006, 021, 025, 026, 028, 031 | Implementada |
| 036 | Descarga automática de datasets (API REST de Roboflow) y `dataset prepare` | 007, 019, 028, 031 | Implementada |
| 037 | Métrica del detector de placas sobre dataset (`evaluate-detector`) | 014, 015, 029, 031 | Implementada |
| 038 | Auditoría de confirmadas y métricas desde la revisión (`evaluate-review`) | 027, 029, 034 | Implementada |
| 039 | Mezcla real + sintético y aceptación del OCR (`evaluate-ocr`) | 031, 032, 033 | Implementada |

## 3. GUI de escritorio PySide6 (040–049)

La GUI se **retirará** cuando la web (sección 5) la iguale (spec 069).

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 040 | Progreso y cancelación de `ProcessVideo` | 024 | Implementada |
| 041 | Búsqueda de avistamientos y corridas (`SightingBrowser`) | 005, 020 | Implementada |
| 042 | GUI: dependencia, arranque, sesión y ventana | 028, 041 | Implementada |
| 043 | GUI: pestaña Procesar | 040, 041, 042 | Implementada |
| 044 | GUI: avistamientos y revisión en diálogo Qt | 038, 041, 042, 043 | Implementada |
| 045 | GUI: exportar, retención y métricas | 025, 026, 038, 042–044 | Implementada |
| 046 | `DecideSighting`: decidir sobre un avistamiento | 027 | Implementada |
| 047 | GUI: tema, tarjeta de placa y cuadrícula | 042, 044 | Implementada |
| 048 | GUI: página Lecturas (galería con panel de revisión) | 041, 046, 047 | Implementada |
| 049 | GUI: ventana rediseñada y flujo de procesar | 043, 045, 047, 048 | Implementada |

## 4. Enfoque nuevo: placas cercanas y legibles, modos de cámara (056–065)

Diseño en `docs/09-enfoque-versatil.md` y ADR-017; `docs/08` §2–§3 aporta el filtro de legibilidad. Las dependencias de la
056 en adelante son las del §5 de docs/09.

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 050 | La corrección posicional no reemplaza una lectura ya válida (`CORRECTION_CONFLICT`) | 004 | Implementada |
| 051 | Cada track conserva sus mejores lecturas (ancho de placa, nitidez) | 023, 024 | Implementada |
| 052 | Decisión "placa borrosa": estado `illegible` y migración de esquema v1 → v2 | 020, 027, 034, 038, 046 | Implementada |
| 053 | GUI: botón y filtro "Placa borrosa" | 046–048, 052 | Implementada |
| 054 | Entrenamiento OCR: mezcla con test congelado y split `test_video` | 035, 039 | Implementada |
| 055 | `dataset export-legibility`: dataset de legibilidad (clase, métricas, sin texto de placa). Ejecutado el 2026-10-03: 1 141 filas (354 legibles, 424 borrosas, 363 no-placa) | 035, 052 | Implementada |
| **056** | Modos de cámara en la configuración: `mode` (`estatico`/`movil`) y `camera_motion_compensation` por perfil, validación "móvil exige CMC", perfil `patrulla`, `TrackerSettings.enable_cmc` | 006, 016, 028 | **Implementada** (2026-10-03, Haiku) |
| 057 | Filtro de cercanía antes de leer: `near_min_width_frac` 0,025, `max_plate_vehicle_ratio` 0,5, `roi`, placa en borde, `min_plate_width_px` 32 | 051, 056 | **Implementada** (2026-10-03, implementador Haiku) |
| 058 | Evaluación con cercanía: ground truth versión 2 (`max_plate_width_px`, cámara `vehicle_mounted`); requiere aprobar el cambio de M-02/M-03 en docs/04 | 029, 057, 059 | Redactada, bloqueada (aprobación de docs/04) |
| 059 | Características de calidad por avistamiento (ancho/alto de placa, nitidez, contraste), `duplicate_of` y migración v2 → v3 | 052, 055, 057 | Implementada |
| 060 | Parada temprana por track (`early_stop`): un track lleno que ya se confirmaría deja de leerse | 051, 056, 057 | Implementada |
| 061 | Duplicados de la misma placa en la corrida (`dedup_window_ms` 30 000 ms): marca `duplicate_of`, oculta por defecto | 041, 059, 060 | Implementada |
| 062 | Entrena el filtro de legibilidad (`training/legibility`) solo con la población cercana; línea base `num_readings` ≤ 1 | 055, 059 | Implementada |
| 063 | Filtro de legibilidad en el pipeline: razones `PREDICTED_ILLEGIBLE` / `PREDICTED_NOT_PLATE`; nunca confirma ni borra | 057, 059, 062 | Implementada |
| 064 | Vista "solo legibles": oculta `PREDICTED_*` y duplicados; pestaña "Ocultas por baja calidad" | 038, 041, 061, 063 | Implementada |
| 065 | Tipo de vehículo por la forma de la placa (bloqueada: dimensiones oficiales PENDIENTES DE VALIDAR) | 013, 015, 057 | Bloqueada: dimensiones oficiales de placa sin verificar |

Criterio de aceptación del filtro de legibilidad (docs/09 §4.2): se mide solo sobre la población cercana; legibles
escondidas por error ≤ 5 %; con ese umbral, ≥ 60 % de borrosas y no-placas ocultadas; mínimo 100 ejemplos por clase en
≥ 4 grupos de video; debe superar la regla "`num_readings` ≤ 1". Lo decide un revisor Opus independiente.

## 5. Interfaz web local (066–073)

Web FastAPI + React (UI diseñada en Figma Make, que solo diseña), ligada a 127.0.0.1, con token por sesión. Antes se
redactan **ADR-016** y **SEG-28**. Sustituye a la GUI PySide6. La 066 expone `mode` en `/api/profiles` y `duplicates`
en `/api/sightings`; el Anexo A de docs/08 ya está actualizado.

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 066 | API de lectura: app factory, token, cabeceras, `videos`, `profiles`, `runs`, `sightings`, `crop`, `summary` | ADR-016/SEG-28, 041, 046, 056, 059, 061, 064 | Implementada |
| 067 | API de acciones: trabajos de procesamiento en hilo + SSE + cancelación, decisiones, export, purga, métricas | 025, 026, 038, 040, 046, 066 | Implementada |
| 068 | Script `lector-web`: 127.0.0.1, puerto libre, abre el navegador con el token, sirve `frontend/dist/` | 066, 067 | Implementada |
| 069 | Modo demo sintético (`lector-web --demo`) | 059, 061, 066, 067, 068 | Implementada |
| 070 | Frontend de Figma Make en `frontend/` conectado a la API real (sin plugins de Figma ni analítica; npm, versiones exactas) | 066–069, 076 | Implementada |
| 071 | Pruebas del frontend: Vitest + Testing Library y Playwright (Chromium) contra `lector-web --demo`, sin violaciones de CSP | 064, 069, 070, 076 | Implementada |
| 072 | Publicación: capturas del modo demo (Playwright) y chequeo de nivel F «web solo en loopback» | 068, 069, 071 | Redactada |
| 073 | Retirar la GUI PySide6 (solo cuando la web cubra sus funciones) | 071 | Redactada |

## 6. Docker (074–075)

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 074 | Clave maestra desde archivo (`LECTOR_KEY_FILE`, `lector key export-file`/`init-file`) | 008, 028 | Implementada |
| 075 | `Dockerfile` multi-etapa y `compose.yaml` (perfiles cpu/gpu), puerto solo en loopback | 068, 074 | Bloqueada: frontend (070) e imágenes base sin verificar |
| 076 | API para el frontend: video original por SHA-256 (Range), fotograma completo, conteos por pestaña, métricas por corrida, ajustes | 066, 067, 068 | Implementada |

---

## Orden de trabajo (docs/09 §5)

1. **056 → 057** (modos y cercanía), con 058 y 059 en paralelo después; luego 060 y 061 (si ambas tocan
   `process_video.py`, primero la 060).
2. Filtro de legibilidad: **062 → 063 → 064** (necesita datos nuevos revisados con el sistema de cercanía).
3. Web: ADR-016 y SEG-28, luego **066 → 069**; diseño en Figma Make (usuario); **070 → 072**; **073** retira la GUI.
4. **074 → 075** (Docker). **065** cuando la normativa de placas esté verificada.

Pendientes del usuario que bloquean validar (docs/09 §8): clasificar los videos de `videos/` (fijo, en mano, en vehículo),
grabar material desde un vehículo (modo móvil no validado hasta E6), base legal de un uso policial, aprobar el cambio de
M-02/M-03 a "placas cercanas". `export-legibility` ya se ejecutó el 2026-10-03; se repite después de la 059.
