# ADR-006 — Muestreo de frames y perfiles de escenario

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-01, RF-03, RNF-01; video dinámico (fps variable, >60 km/h)

## Contexto
Los videos de celular tienen fps variable (VFR): el índice de frame no es una medida de tiempo.
A 60 km/h un vehículo avanza 16,7 m/s; a mayor velocidad hay menos frames útiles por placa.
El presupuesto de 1× obliga a no leer OCR en todos los frames.

## Opciones evaluadas
1. Procesar todos los frames: máximo recall, riesgo de no cumplir 1× con videos de 60 fps.
2. Cada N frames fijo: incorrecto con VFR.
3. **Muestreo por timestamp** a `target_fps` por perfil + **lectura dirigida por track** (solo se
   lee OCR en tracks que aún no tienen suficientes lecturas).

## Decisión
- `TimeBasedFrameSampler`: procesa un frame si `timestamp_ms - último_procesado_ms >=
  1000 / target_fps - 1` (tolerancia de 1 ms); el primer frame siempre se procesa.
- Perfiles (valores iniciales **provisionales**, se calibran en Fase 5):

| Parámetro | parqueadero | calle_lenta | calle_rapida |
|---|---|---|---|
| `target_fps` | 10 | 15 | 30 |
| `max_readings_per_track` | 8 | 8 | 6 |
| `track_finalize_after_ms` | 3000 | 2000 | 1000 |
| `min_readings` (consolidación) | 3 | 3 | 2 |
| `confirm_threshold` | 0.90 | 0.90 | 0.90 |
| `min_agreement` | 0.60 | 0.60 | 0.60 |
| `min_plate_width_px` | 20 | 20 | 20 |
| `min_sharpness` | 0.0 | 0.0 | 0.0 |
| `max_ocr_per_frame` | 8 | 8 | 8 |
| `vehicle_crop_margin` | 0.10 | 0.10 | 0.10 |

- `min_sharpness = 0.0` desactiva el filtro hasta calibrarlo; la nitidez se usa igual para elegir el
  mejor recorte.

## Consecuencias
- (+) Correcto con VFR; costo controlado; perfiles cambian comportamiento sin código.
- (−) Umbrales iniciales sin calibrar: las metas M-01..M-03 se validan en Fase 5.
- (Enmienda 2026-09-27, spec 051) `max_readings_per_track` es el número de lecturas que se votan, no
  el de lecturas que se hacen: el track se sigue leyendo mientras está activo y conserva las de mayor
  (ancho de placa, nitidez). Motivo: con las primeras N se votaban los frames lejanos y borrosos
  (docs/historial/07 §1, hallazgo 4). Coste: detección de placa y OCR en cada frame muestreado por track activo,
  acotado por `max_ocr_per_frame`; los tracks sin lecturas suficientes tienen prioridad. M-05 se
  vuelve a medir en la Fase 2 de docs/historial/07.
- (Enmienda 2026-10-03, ADR-017, specs 056–057) Cada perfil declara `mode` (`estatico`/`movil`) y
  `camera_motion_compensation`; perfil nuevo `patrulla` (`movil`). Filtro de cercanía antes de leer:
  ROI, tamaño del vehículo (`max_plate_vehicle_ratio` 0,5) antes del tope `max_ocr_per_frame`, placa
  a menos de 2 px del borde y ancho mínimo efectivo `ceil(max(min_plate_width_px, near_min_width_frac ×
  lado mayor))`, con `min_plate_width_px` 32 y `near_min_width_frac` 0,025 en los cuatro perfiles.
