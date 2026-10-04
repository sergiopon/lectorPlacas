# 060 - Parada temprana por track (`early_stop`)

## Objetivo
Dejar de leer un track cuando ya está lleno y sus lecturas actuales ya se confirmarían. Hoy (spec 051) un vehículo
detenido frente a la cámara se lee en cada frame muestreado mientras sigue a la vista. Con `early_stop`, después de cada
lectura añadida a un track **lleno** se consolidan sus lecturas actuales; si el resultado es `CONFIRMED`, el track queda
**resuelto** y no pide más lecturas hasta finalizar. Se sigue observando (última aparición y votos de tipo) y al
finalizar se consolida como hoy.

## Depende de
051, 056, 057.

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §1.6 y §4.3 (D7); ADR-006 (spec 051); ADR-007 (consolidación, sin cambios).
- docs/03-modelo-datos.md §4 (campo de perfil).

## Archivos a crear/modificar
- `src/lector_placas/application/track_registry.py`
- `src/lector_placas/application/process_video.py`
- `src/lector_placas/infrastructure/config.py`
- `src/lector_placas/cli/composition.py`
- `config/lector.yaml`
- `tests/unit/application/test_track_registry_early_stop.py` (nuevo)
- `tests/unit/application/test_process_video_early_stop.py` (nuevo)
- `tests/unit/infrastructure/test_config.py` (un test nuevo)
- `tests/unit/cli/test_processing_settings.py` (un cambio de expectativa)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `application/track_registry.py`
- `_TrackState` gana el campo `resolved: bool`, que `_new_state` inicia a `False`.
- Métodos públicos nuevos de `TrackRegistry`:
  - `def readings(self, track_id: int) -> tuple[PlateReading, ...]`: lecturas actuales del track, ordenadas por
    `(timestamp_ms, frame_index)` (el mismo orden que `FinalizedTrack.readings`).
  - `def vehicle_type(self, track_id: int) -> VehicleType`: tipo dominante actual, con la misma regla que
    `_dominant_type`.
  - `def mark_resolved(self, track_id: int) -> None`: marca el track como resuelto.
  - Los tres lanzan `InvalidEntityError(f"track inexistente: {track_id}")` si el track no existe.
- `needs_reading(track_id)` pasa a devolver `True` si y solo si el track existe **y no está resuelto**.
- `observe`, `is_full`, `add_reading`, `pop_inactive`, `pop_all` y `FinalizedTrack` no cambian.

### `application/process_video.py`
`ProcessingSettings` gana, **al final** (después de `roi`), `early_stop: bool = False`. Con `False` el comportamiento es
idéntico al actual.

### `infrastructure/config.py` y `cli/composition.py`
- `ProfileConfig` gana, **al final** (después de `roi`), `early_stop: bool`, sin valor por defecto.
- `build_processing_settings` pasa además `early_stop=profile.early_stop`.

## Comportamiento esperado
1. En `ProcessVideo._record_readings`, justo después de cada `registry.add_reading(reading, candidate.crop)`, si
   `settings.early_stop` es `True` **y** `registry.is_full(track_id)` es `True`:
   1. `plate = deps.consolidator.consolidate(registry.readings(track_id), registry.vehicle_type(track_id))`.
   2. Si `plate.status is ReviewStatus.CONFIRMED` → `registry.mark_resolved(track_id)`.
   3. El resultado `plate` se descarta: no se persiste ni se registra en log. Una excepción del consolidador se propaga
      como hoy en la finalización.
2. Un track resuelto queda fuera de `eligible` en los frames siguientes porque `needs_reading` devuelve `False`; no gasta
   detector de placas ni OCR. Sigue en el registro y se finaliza por inactividad o al final del video como cualquier otro.
3. Al finalizar, `_save_track` consolida todas sus lecturas (sin cambios); el resultado puede diferir del de la parada
   temprana solo si cambia el tipo dominante del vehículo después de resolverse, y se guarda el de la finalización.
4. `config/lector.yaml`: en los cuatro perfiles se añade `early_stop: true` como **última** clave del perfil (después
   de `roi`). Nada más cambia.

## Casos borde y manejo de errores
- Track no lleno: nunca se consolida antes de tiempo, aunque sus lecturas ya coincidan.
- Track lleno cuya consolidación sale `UNVERIFIED`: sigue leyéndose; cada lectura nueva que se añada o reemplace a otra
  dispara de nuevo la comprobación (aunque la lectura nueva se haya descartado por ser peor, la comprobación se hace igual
  tras `add_reading`).
- `early_stop: false` en un perfil: comportamiento de la spec 051.

## Tests de aceptación (en prosa)
Fixtures sintéticos.

**Test existente que cambia de expectativa (solo este):**
- `tests/unit/cli/test_processing_settings.py::test_build_processing_settings_copies_profile` (spec 057): además comprueba
  `early_stop is True`.

`tests/unit/application/test_track_registry_early_stop.py` (lecturas `PlateReading` sintéticas con textos inventados):
- `test_mark_resolved_stops_needs_reading`: tras `observe` de un track y `mark_resolved`, `needs_reading` es `False`;
  otro track observado sigue con `needs_reading` `True`.
- `test_resolved_track_is_still_observed_and_finalized`: un track resuelto observado en 0 ms y en 500 ms se finaliza con
  `pop_all` con `last_seen_ms == 500` y sus lecturas.
- `test_readings_are_sorted`: lecturas añadidas en los tiempos 300, 100 y 200 ms se devuelven en el orden 100, 200, 300.
- `test_vehicle_type_is_dominant`: con 2 observaciones como `CAR` y 1 como `MOTORCYCLE`, `vehicle_type` devuelve `CAR`.
- `test_unknown_track_raises`: `readings`, `vehicle_type` y `mark_resolved` sobre un track inexistente lanzan
  `InvalidEntityError`.

`tests/unit/application/test_process_video_early_stop.py`: reutiliza por importación desde
`tests.unit.application.test_process_video` las clases `FakeSource`, `FakeSourceFactory`, `ScriptedVehicleDetector`,
`SingleTrackTracker`, `FixedPlateDetector`, `CyclingReader`, `ConstantQuality` y `SHA`, con un `build` propio igual al de
ese archivo pero que añade `early_stop` y `max_readings_per_track` como parámetros con nombre (consolidador con
`ConsolidationPolicy(3, 0.9, 0.6, 0.1)`).
- `test_early_stop_after_confirmed_full_track`: 10 frames, `max_readings_per_track=3`, `early_stop=True`, lector
  `CyclingReader(["ABC123"])`: el lector recibe exactamente 3 llamadas; se guarda un avistamiento `CONFIRMED` con
  `num_readings == 3` y `last_seen_ms == 900`.
- `test_no_early_stop_reads_every_frame`: igual pero con `early_stop=False`: el lector recibe 10 llamadas.
- `test_unconfirmed_full_track_keeps_reading`: igual que el primero pero con lector
  `CyclingReader(["ABC123", "ABD123", "ABE123"])`: el lector recibe 10 llamadas y el avistamiento queda `UNVERIFIED`.

`tests/unit/infrastructure/test_config.py` (añadir):
- `test_real_config_early_stop`: los cuatro perfiles de `load_config(REAL)` tienen `early_stop is True`; borrar
  `early_stop` de `calle_lenta` hace que `load_config` lance `ConfigurationError`.

## Fuera de alcance
- Medir el efecto en velocidad y confirmaciones (experimento E5 de docs/09).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde; solo cambia el test listado.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
