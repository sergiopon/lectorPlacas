# ADR-004 — Tracker

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-04, RF-08, RF-21

## Contexto
El video puede venir de cámara fija o de un celular en mano (cámara en movimiento, sin declararlo),
con fps variable. Se necesita un ID por vehículo para agrupar lecturas y generar un avistamiento por paso.

## Opciones evaluadas
| Opción | CMC (cámara móvil) | Desacoplado del detector | Licencia |
|---|---|---|---|
| Trackers integrados de Ultralytics (`model.track`) | BoT-SORT con GMC | No (acoplado al modelo PyTorch) | AGPL-3.0 |
| boxmot 25.0.0 | Sí | Sí | AGPL-3.0; no declara Python 3.14 |
| `supervision.ByteTrack` | No | Sí | MIT; deprecado en 0.28, se elimina en 0.31 |
| **`trackers` 2.6.0 `BoTSORTTracker`** | Sí (`enable_cmc`, `sparseOptFlow`/`orb`/`sift`/`ecc`) | Sí (`sv.Detections`) | Apache-2.0 |

Verificado en el código de `trackers` 2.6.0: `update(detections: sv.Detections, frame: np.ndarray | None,
timestamp: float | None) -> sv.Detections`; devuelve el subconjunto de las detecciones de entrada
(conserva `class_id` y `confidence`) con `tracker_id` (≥ 0 confirmados, −1 no confirmados);
`timestamp` en segundos soporta fps variable; `reset()` limpia el estado.

## Decisión
`trackers.BoTSORTTracker` con CMC **siempre activo** (`cmc_method="sparseOptFlow"`,
`cmc_downscale=2`) y `timestamp = timestamp_ms / 1000`. Se ignoran salidas con `tracker_id == -1`.
Resto de parámetros: los valores por defecto de la librería, expuestos en configuración.

## Consecuencias
- (+) Funciona con cámara fija y móvil sin configuración; tiempo real con VFR.
- (−) Añade `supervision`, `scipy`, `opencv-python`, `requests` como dependencias transitivas (`scipy` ya no se declara en `pyproject.toml`).
  `requests` no se usa en runtime (guardia de red, ADR-012).
- (−) CMC tiene costo por frame; se mide en Fase 5.

## Actualización 2026-10-03 (ADR-017)
La CMC deja de estar «siempre activa»: es el campo `camera_motion_compensation` de cada perfil, que `build_tracker`
pasa a `TrackerSettings.enable_cmc`. Los perfiles de modo `movil` la exigen en `true`; los cuatro perfiles actuales la
dejan en `true` hasta que el experimento E3 permita apagarla en estático. `cmc_method` y `cmc_downscale`
siguen siendo globales en `tracker:`.
