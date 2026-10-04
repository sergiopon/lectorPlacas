# 057 - Filtro de cercanía antes de leer

## Objetivo
Leer solo placas **cercanas**: antes de detectar la placa y de leerla se descartan los vehículos fuera de la zona de
interés (ROI) y los demasiado pequeños; después de detectarla se descartan las placas cortadas por el borde del frame y
las más estrechas que el **ancho mínimo efectivo**. Un track que nunca pasa el filtro no tiene lecturas y no se guarda.
Al terminar cada corrida se registra una línea de log con los descartes de cada paso.

## Depende de
051, 056.

## Archivos rectores aplicables
- ADR-017 (decisión 1), docs/09-enfoque-versatil.md §1.2–§1.4 y §2.2–§2.3.
- docs/03-modelo-datos.md §4 (campos de perfil). ADR-006 (actualización 2026-10-03).
- reglas-seguridad.md SEG-05 (la línea de log nueva no lleva texto de placa).

## Archivos a crear/modificar
- `src/lector_placas/application/proximity.py` (nuevo)
- `src/lector_placas/application/process_video.py`
- `src/lector_placas/infrastructure/config.py`
- `src/lector_placas/cli/composition.py`
- `config/lector.yaml`
- `tests/unit/application/test_proximity.py` (nuevo)
- `tests/unit/application/test_process_video_proximity.py` (nuevo)
- `tests/unit/infrastructure/test_config.py`
- `tests/unit/cli/test_processing_settings.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `application/proximity.py` (nuevo; solo stdlib y `domain`)
- `FRAME_EDGE_MARGIN_PX: Final[int] = 2`
- `FULL_FRAME_ROI: Final[tuple[float, float, float, float]] = (0.0, 0.0, 1.0, 1.0)`
- `NEAR_MIN_WIDTH_FRAC_MAX: Final[float] = 0.2`
- `def effective_min_width(frame_width: int, frame_height: int, min_plate_width_px: int, near_min_width_frac: float) -> int`
- `def center_in_roi(box: BoundingBox, roi: tuple[float, float, float, float], frame_width: int, frame_height: int) -> bool`
- `def touches_frame_edge(box: BoundingBox, frame_width: int, frame_height: int) -> bool`
- `def validate_roi(roi: tuple[float, float, float, float]) -> None`
- `@dataclass(slots=True) class ProximityCounters` con seis campos `int`, todos con valor por defecto `0`, en este orden:
  `outside_roi`, `small_vehicle`, `no_plate`, `plate_at_edge`, `narrow_plate`, `blurry`.

### `application/process_video.py`
`ProcessingSettings` gana tres campos **al final**, con valor por defecto, en este orden:
- `near_min_width_frac: float = 0.0`
- `max_plate_vehicle_ratio: float = 1.0`
- `roi: tuple[float, float, float, float] = FULL_FRAME_ROI` (importado de `proximity`)

Con esos valores por defecto el comportamiento es idéntico al actual (salvo el paso de placa en borde, que siempre se
aplica). Los tests existentes que construyen `ProcessingSettings` con 7 argumentos no cambian.

### `infrastructure/config.py`
`ProfileConfig` gana tres campos **al final** (después de `vehicle_crop_margin`), sin valor por defecto, en este orden:
`near_min_width_frac: float`, `max_plate_vehicle_ratio: float`, `roi: tuple[float, float, float, float]`.

### `cli/composition.py`
Función nueva `def build_processing_settings(name: str, profile: ProfileConfig) -> ProcessingSettings`, que
`build_process_video` usa en lugar de construir `ProcessingSettings` en línea.

## Comportamiento esperado

### 1. Funciones de `proximity.py`
1. `effective_min_width`: devuelve
   `math.ceil(round(max(float(min_plate_width_px), near_min_width_frac * max(frame_width, frame_height)), 6))`.
   El `round(…, 6)` evita que un error de coma flotante (p. ej. `48.00000000000001`) suba una unidad.
2. `center_in_roi`: `cx = (box.x1 + box.x2) / 2`, `cy = (box.y1 + box.y2) / 2`; devuelve
   `roi[0] * frame_width <= cx <= roi[2] * frame_width and roi[1] * frame_height <= cy <= roi[3] * frame_height`
   (bordes incluidos).
3. `touches_frame_edge`: devuelve `True` si `box.x1 < FRAME_EDGE_MARGIN_PX`, o `box.y1 < FRAME_EDGE_MARGIN_PX`, o
   `box.x2 > frame_width - FRAME_EDGE_MARGIN_PX`, o `box.y2 > frame_height - FRAME_EDGE_MARGIN_PX`; si no, `False`.
4. `validate_roi`: si no se cumple `0.0 <= roi[0] < roi[2] <= 1.0 and 0.0 <= roi[1] < roi[3] <= 1.0`, lanza
   `ValueError("roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1")`.

### 2. Validación de `ProcessingSettings.__post_init__` (se añade al final de la existente)
1. Si no `0.0 <= near_min_width_frac <= NEAR_MIN_WIDTH_FRAC_MAX` →
   `InvalidEntityError(f"near_min_width_frac debe estar en [0, 0.2]: {near_min_width_frac}")`.
2. Si no `0.0 < max_plate_vehicle_ratio <= 1.0` →
   `InvalidEntityError(f"max_plate_vehicle_ratio debe estar en (0, 1]: {max_plate_vehicle_ratio}")`.
3. `validate_roi(roi)`; un `ValueError` se relanza como `InvalidEntityError` con el mismo mensaje (`from` el original).

### 3. Validación de `ProfileConfig` (validadores de campo nuevos)
- `near_min_width_frac` fuera de [0, 0,2] → `ValueError(f"near_min_width_frac debe estar en [0, 0.2]: {value}")`.
- `max_plate_vehicle_ratio` fuera de (0, 1] → `ValueError(f"max_plate_vehicle_ratio debe estar en (0, 1]: {value}")`.
- `roi`: llama a `validate_roi(value)` y deja pasar su `ValueError`. (`config.py` puede importar `application`.)
Una `roi` con un número de elementos distinto de 4 la rechaza pydantic por el tipo.

### 4. `ProcessVideo`, por frame muestreado (sustituye a `_collect_candidates` y `_plate_candidate`)
`ProcessVideo` guarda un `ProximityCounters` nuevo por corrida (se crea en `_run`, junto a `_Counters`, y se pasa a
los métodos que lo usan). Para cada frame, después de `registry.observe` (sin cambios):
1. `min_width = effective_min_width(frame.width, frame.height, settings.min_plate_width_px, settings.near_min_width_frac)`.
2. `eligible` = tracks del frame con `registry.needs_reading(track_id)` (sin cambios), en el orden en que los devuelve el
   tracker.
3. **ROI.** Por cada track de `eligible`: si `center_in_roi(track.box, settings.roi, frame.width, frame.height)` es
   `False` → `counters.outside_roi += 1` y se descarta.
4. **Tamaño del vehículo.** Por cada track que sigue: si `track.box.width < min_width / settings.max_plate_vehicle_ratio`
   → `counters.small_vehicle += 1` y se descarta. (`track.box` es la caja sin margen; división en coma flotante.)
5. **Orden y tope.** Con los que quedan, el orden de la spec 051 sin cambios
   (`key=lambda t: (registry.is_full(t.track_id), -t.box.area)`) y se toman los `max_ocr_per_frame` primeros.
6. Por cada track elegido, en ese orden:
   1. `vbox = _expand_vehicle_box(...)` (sin cambios). Si es `None` → `counters.small_vehicle += 1` y se descarta.
   2. Detección de placa en el recorte del vehículo (sin cambios). Si no hay detecciones, o la caja trasladada y
      recortada al frame es `None` → `counters.no_plate += 1` y se descarta. Se elige la de mayor confianza (sin
      cambios).
   3. **Borde.** Si `touches_frame_edge(pbox, frame.width, frame.height)` → `counters.plate_at_edge += 1` y se descarta.
   4. **Ancho.** Si `pbox.width < min_width` → `counters.narrow_plate += 1` y se descarta. (Sustituye a la comparación
      con `min_plate_width_px` de `_best_plate_box`, que deja de recibir ese parámetro.)
   5. **Nitidez.** Si `sharpness < settings.min_sharpness` → `counters.blurry += 1` y se descarta (sin cambios en el
      cálculo).
   6. Si pasa, es candidato (sin cambios en `_PlateCandidate` ni en la lectura posterior).

### 5. Línea de log al cerrar la corrida
En `_finish_run`, **antes** del `logger.info` de `corrida terminada`, se registra exactamente:
`logger.info("cercania run_id=%d fuera_roi=%d vehiculo_pequeno=%d sin_placa=%d placa_en_borde=%d placa_estrecha=%d borrosa=%d", run_id, c.outside_roi, c.small_vehicle, c.no_plate, c.plate_at_edge, c.narrow_plate, c.blurry)`.
En una corrida fallida o cancelada no se registra.

### 6. Configuración y composición
- `config/lector.yaml`: en los cuatro perfiles (`parqueadero`, `calle_lenta`, `calle_rapida`, `patrulla`),
  `min_plate_width_px` pasa de `20` a `32` y se añaden, **después** de `vehicle_crop_margin` y en este orden:
  `near_min_width_frac: 0.025`, `max_plate_vehicle_ratio: 0.5` y `roi: [0.0, 0.0, 1.0, 1.0]`. Nada más cambia.
- `build_processing_settings(name, profile)` devuelve
  `ProcessingSettings(name, profile.max_ocr_per_frame, profile.min_plate_width_px, profile.min_sharpness, profile.vehicle_crop_margin, profile.track_finalize_after_ms, profile.max_readings_per_track, near_min_width_frac=profile.near_min_width_frac, max_plate_vehicle_ratio=profile.max_plate_vehicle_ratio, roi=profile.roi)`.

## Casos borde y manejo de errores
- Ancho de placa igual a `min_width`: pasa. Ancho de vehículo igual a `min_width / ratio`: pasa. Centro sobre el borde
  de la ROI: dentro.
- Placa con `x1` exactamente 2,0 o `x2` exactamente `ancho − 2`: no toca el borde.
- `near_min_width_frac = 0.0` deja solo el piso `min_plate_width_px`.
- Un track descartado en un frame puede pasar en otro: el descarte es por frame, no por track.
- La línea `cercania` no contiene texto de placa.

## Tests de aceptación (en prosa)
Fixtures sintéticos. Ningún test existente se modifica.

`tests/unit/application/test_proximity.py`:
- `test_effective_min_width` (parametrizado): `(1280, 720, 32, 0.025) → 32`; `(1920, 1080, 32, 0.025) → 48`;
  `(1080, 1920, 32, 0.025) → 48`; `(3840, 2160, 32, 0.025) → 96`; `(1920, 1080, 32, 0.0) → 32`;
  `(1920, 1080, 32, 0.02) → 39`; `(1920, 1080, 20, 0.015) → 29`.
- `test_center_in_roi_border_included`: caja `(0, 0, 100, 100)`, frame 1000×1000: con ROI `(0.05, 0.0, 1.0, 1.0)` está
  dentro (centro x = 50 = 0,05 × 1000); con ROI `(0.051, 0.0, 1.0, 1.0)` está fuera; con ROI `(0.0, 0.0, 1.0, 0.04)`
  está fuera.
- `test_touches_frame_edge` (parametrizado, frame 640×480): `(2, 2, 638, 478) → False`; `(1.9, 10, 100, 50) → True`;
  `(10, 1.5, 100, 50) → True`; `(10, 10, 638.1, 50) → True`; `(10, 10, 100, 478.5) → True`.
- `test_validate_roi`: `(0.0, 0.0, 1.0, 1.0)` no lanza; `(0.5, 0.0, 0.4, 1.0)`, `(0.0, 0.0, 1.0, 1.1)`,
  `(-0.1, 0.0, 1.0, 1.0)` y `(0.0, 0.5, 1.0, 0.5)` lanzan `ValueError` con el mensaje exacto del comportamiento 1.4.
- `test_processing_settings_defaults_and_validation`: `ProcessingSettings("p", 8, 20, 0.0, 0.10, 2000, 8)` tiene
  `near_min_width_frac == 0.0`, `max_plate_vehicle_ratio == 1.0` y `roi == (0.0, 0.0, 1.0, 1.0)`; con
  `near_min_width_frac=0.3`, con `max_plate_vehicle_ratio=0.0` y con `roi=(0.5, 0.0, 0.4, 1.0)` lanza
  `InvalidEntityError`.

`tests/unit/application/test_process_video_proximity.py`: reutiliza por importación desde
`tests.unit.application.test_process_video` las clases `FakeSource`, `FakeSourceFactory`, `ScriptedVehicleDetector`,
`SingleTrackTracker`, `FixedPlateDetector`, `TwoTrackTracker`, `CyclingReader` y `ConstantQuality`, y las constantes
`SHA`. Define un `build` propio con las mismas dependencias que el `build` de ese archivo (sampler a 10 fps, consolidador
con `ConsolidationPolicy(3, 0.9, 0.6, 0.1)`, `FakeClock(step_ms=10)`) y `ProcessingSettings("calle_lenta",
max_ocr_per_frame, min_plate_width_px, min_sharpness, 0.10, 2000, max_readings_per_track, near_min_width_frac=…,
max_plate_vehicle_ratio=…, roi=…)`, con todos estos valores como parámetros con nombre (por defecto: 8, 20, 0.0, 8,
0.0, 1.0, `(0.0, 0.0, 1.0, 1.0)`). Define además `BoxVehicleDetector(box)` (devuelve siempre
`[VehicleDetection(box, 0.9, VehicleType.CAR)]`) y `BoxPlateDetector(box)` (devuelve siempre
`[PlateDetection(box, 0.9)]` y cuenta sus llamadas). El frame es 640×480 (de `FakeSource`). Con la caja de vehículo por
defecto `(100, 100, 300, 250)` y la placa por defecto, la placa queda en el frame en `(130, 185, 230, 215)`: 100 px.
- `test_outside_roi_skips_detection_and_reading`: 3 frames, ROI `(0.5, 0.0, 1.0, 1.0)` (centro del vehículo x = 200 <
  320). El detector de placas no recibe ninguna llamada; `tracks_without_reading == 1`; no hay avistamientos.
- `test_small_vehicle_skips_plate_detector`: 3 frames, `near_min_width_frac=0.2` (mínimo 128 px),
  `max_plate_vehicle_ratio=0.5` (vehículo mínimo 256 px > 200). El detector de placas no recibe llamadas; no hay
  avistamientos.
- `test_narrow_plate_is_discarded`: 3 frames, `near_min_width_frac=0.2`, `max_plate_vehicle_ratio=1.0`. El detector
  de placas recibe 3 llamadas; el lector, 0; no hay avistamientos.
- `test_plate_at_edge_is_discarded`: `BoxVehicleDetector((0, 100, 200, 250))` y `BoxPlateDetector((1, 100, 101, 130))`
  (en el frame, `x1 = 1 < 2`), 3 frames. El lector recibe 0 llamadas; no hay avistamientos.
- `test_near_plate_is_read`: 10 frames con los valores por defecto del `build` pero `min_plate_width_px=32`,
  `near_min_width_frac=0.025` (mínimo `max(32, 16) = 32`), `max_plate_vehicle_ratio=0.5` (vehículo mínimo 64 ≤ 200). Se
  guarda un avistamiento `CONFIRMED` con texto `ABC123`.
- `test_roi_filter_runs_before_ocr_cap`: `TwoTrackTracker` (track 1 pequeño con centro x = 500; track 2 grande con
  centro x = 250), ROI `(0.0, 0.0, 0.65, 1.0)` (límite x = 416), `max_ocr_per_frame=1`, `max_readings_per_track=1`, 2
  frames. Hay un solo avistamiento, del track 2; `tracks_total == 2` y `tracks_without_reading == 1`; el detector de
  placas recibe 2 llamadas.
- `test_proximity_log_line` (con `caplog` a nivel INFO): tres corridas independientes de 3 frames cada una, y en cada
  una la línea de log que empieza por `cercania ` es exactamente:
  - ROI `(0.5, 0.0, 1.0, 1.0)` → `cercania run_id=1 fuera_roi=3 vehiculo_pequeno=0 sin_placa=0 placa_en_borde=0 placa_estrecha=0 borrosa=0`
  - `FixedPlateDetector(found=False)` → `cercania run_id=1 fuera_roi=0 vehiculo_pequeno=0 sin_placa=3 placa_en_borde=0 placa_estrecha=0 borrosa=0`
  - `min_sharpness=60.0` (`ConstantQuality` da 50) → `cercania run_id=1 fuera_roi=0 vehiculo_pequeno=0 sin_placa=0 placa_en_borde=0 placa_estrecha=0 borrosa=3`
- `test_no_proximity_log_on_failure`: con `ScriptedVehicleDetector(fail_on_call=1)` la corrida lanza
  `InferenceError` y ningún registro de log empieza por `cercania `.

`tests/unit/infrastructure/test_config.py` (añadir; usa `base_data()` y `write()`):
- `test_real_config_proximity_values`: en los cuatro perfiles de `load_config(REAL)`, `min_plate_width_px == 32`,
  `near_min_width_frac == 0.025`, `max_plate_vehicle_ratio == 0.5` y `roi == (0.0, 0.0, 1.0, 1.0)`.
- `test_invalid_proximity_values` (parametrizado, cada caso modifica `calle_lenta`): `near_min_width_frac` 0.21 →
  mensaje contiene `near_min_width_frac debe estar en [0, 0.2]: 0.21`; `near_min_width_frac` -0.01 → contiene
  `near_min_width_frac debe estar en [0, 0.2]: -0.01`; `max_plate_vehicle_ratio` 0.0 → contiene
  `max_plate_vehicle_ratio debe estar en (0, 1]: 0.0`; `max_plate_vehicle_ratio` 1.01 → contiene
  `max_plate_vehicle_ratio debe estar en (0, 1]: 1.01`; `roi` `[0.5, 0.0, 0.4, 1.0]` → contiene
  `roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1`; `roi` `[0.0, 0.0, 1.0]` → lanza
  `ConfigurationError` (sin comprobar el mensaje). En todos, `load_config` lanza `ConfigurationError`.

`tests/unit/cli/test_processing_settings.py` (nuevo):
- `test_build_processing_settings_copies_profile`: con `load_config(REAL)` y el perfil `patrulla`,
  `composition.build_processing_settings("patrulla", perfil)` devuelve un `ProcessingSettings` con
  `profile_name == "patrulla"`, `max_ocr_per_frame == 8`, `min_plate_width_px == 32`, `min_sharpness == 0.0`,
  `vehicle_crop_margin == 0.10`, `track_finalize_after_ms == 1000`, `max_readings_per_track == 6`,
  `near_min_width_frac == 0.025`, `max_plate_vehicle_ratio == 0.5` y `roi == (0.0, 0.0, 1.0, 1.0)`.

## Fuera de alcance
- Guardar el ancho de la placa o la resolución del frame en BD (spec 059).
- Ajustar los umbrales con datos (experimentos E1 y E2 de docs/09): se cambian después en `config/lector.yaml`.
- Usar `mode` en el pipeline: no se usa.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde, sin modificar tests existentes.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `uv run pytest tests/architecture -q` en verde (`proximity.py` solo importa stdlib y `domain`).
