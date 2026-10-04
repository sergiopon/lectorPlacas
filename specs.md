# Specs de lectorPlacas

Resumen de todas las specs: qué hace cada una, de cuáles depende y en qué estado está. Fecha: 2026-10-03.
Fuente de verdad del estado: `specs/README.md`. Las specs 056–071 **aún no están redactadas**: su alcance sale de
`docs/08-plan-legibilidad-y-web.md` y sus dependencias son una **propuesta** (NO VERIFICADO hasta redactarlas).

Estados: **Implementada** (integrada en `main`) · **En implementación** (rama y worktree activos) · **Redactada**
(spec lista, sin implementar) · **Por redactar** (solo existe en el plan).

## Resumen

| Estado | Specs |
|---|---|
| Implementada | 000–055 (56 specs) |
| Por redactar | 056–071 (16 specs, plan `docs/08`) |

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

## 4. Mejora de lectura y legibilidad (050–061)

Planes: `docs/07-plan-mejora-lectura.md` (050–054) y `docs/08-plan-legibilidad-y-web.md` §2–§3 (055–061).

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 050 | La corrección posicional no reemplaza una lectura ya válida (`CORRECTION_CONFLICT`) | 004 | Implementada |
| 051 | Cada track conserva sus mejores lecturas (ancho de placa, nitidez) | 023, 024 | Implementada |
| 052 | Decisión "placa borrosa": estado `illegible` y migración de esquema v1 → v2 | 020, 027, 034, 038, 046 | Implementada |
| 053 | GUI: botón y filtro "Placa borrosa" | 046–048, 052 | Implementada |
| 054 | Entrenamiento OCR: mezcla con test congelado y split `test_video` | 035, 039 | Implementada |
| **055** | **`dataset export-legibility`: exporta todos los avistamientos con estado final, con su clase (legible / borrosa / no_placa) y métricas, sin texto de placa. URGENTE: los primeros recortes caducan el 2026-12-25** | 035, 052 | **Implementada** (2026-10-03, DeepSeek flash) |
| 056 | Guarda por avistamiento ancho/alto de placa, nitidez y contraste (migración v2 → v3, receta de la 052) | 052 (y 018, 051) | Por redactar |
| 057 | Entrena el filtro de legibilidad en `training/legibility` (regresión logística; CNN pequeña si no basta) con reparto por video | 055, 056 | Por redactar |
| 058 | Filtro de legibilidad en el pipeline: añade razón `PREDICTED_ILLEGIBLE` / `PREDICTED_NOT_PLATE`; nunca confirma ni borra | 057 | Por redactar |
| 059 | Vista "solo legibles" con pestaña "Ocultas por baja calidad"; `evaluate-review` informa cuántas ocultas eran legibles | 058, 048 | Por redactar |
| 060 | Parada temprana por track (deja de leer cuando las N mejores lecturas coinciden) | 051 | Por redactar |
| 061 | Tipo de vehículo por la forma de la placa (dimensiones oficiales PENDIENTES DE VALIDAR) | 013, 015 | Por redactar |

Criterio de aceptación del filtro (docs/08 §2.4): legibles escondidas por error ≤ 5 %; con ese umbral, ≥ 60 % de
borrosas y no-placas ocultadas; lo decide un revisor Opus independiente antes de encenderlo.

## 5. Interfaz web local (062–069)

Web FastAPI + React (UI diseñada en Figma Make, que solo diseña), ligada a 127.0.0.1, con token por sesión. Antes de
las specs se redactan **ADR-016** y **SEG-28**. Sustituye a la GUI PySide6.

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 062 | API de lectura: app factory, token, cabeceras, `videos`, `profiles`, `runs`, `sightings`, `crop` | ADR-016/SEG-28, 041, 046 | Por redactar |
| 063 | API de acciones: procesar en hilo + SSE + cancelación, decisiones, export, purga, métricas | 062, 040, 046 | Por redactar |
| 064 | Comando `lector web`: arranque en 127.0.0.1, puerto libre, abre el navegador con el token, sirve `dist/` | 062, 063 | Por redactar |
| 065 | Modo demo sintético (`lector web --demo`): BD temporal y recortes sintéticos | 063 | Por redactar |
| 066 | Importar el frontend exportado de Figma Make a `frontend/` con cliente tipado desde OpenAPI | 062, 065 y el diseño del usuario | Por redactar |
| 067 | Pantallas conectadas y pruebas (Vitest, Playwright contra el modo demo) | 066, 059 | Por redactar |
| 068 | Publicación: README con inicio rápido, capturas del demo, nivel F con `bind` en loopback | 064, 067 | Por redactar |
| 069 | Retirar la GUI PySide6 (solo cuando la web cubra sus funciones) | 067 | Por redactar |

## 6. Docker (070–071)

| # | Qué hace | Depende de | Estado |
|---|---|---|---|
| 070 | `KeyProvider` de archivo (Docker secret): `lector key init --to-file`; actualiza SEG-02/ADR-005 | 008 | Por redactar |
| 071 | `Dockerfile` multi-etapa y `compose.yaml` (perfiles cpu/gpu), puerto solo en loopback | 064, 070 | Por redactar |

---

## Camino crítico y orden propuesto (docs/08 §5)

1. **055** (implementada) → **falta ejecutar `lector dataset export-legibility` con datos reales antes del 2026-12-25**; luego, volver `retention.crops_days` a 30.
2. Operación sin código: anotar un tramo con verdad y calibrar perfiles (docs/07 Fases 1–2); después **060**.
3. Filtro de legibilidad: **056 → 057 → 058 → 059**.
4. En paralelo, backend web: ADR-016 y SEG-28, luego **062 → 063 → 064 → 065**.
5. Diseño en Figma Make (usuario) → **066 → 067 → 068**; **061** puede ir aquí.
6. **069** retirar la GUI; después **070 → 071** (Docker).

Reentrenar el OCR queda bloqueado hasta que `test_video` tenga ≥ 100 recortes revisados.
