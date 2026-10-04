# 056 - Modos de cámara en la configuración (`mode`, `camera_motion_compensation`, perfil `patrulla`)

## Objetivo
Cada perfil de `config/lector.yaml` declara su modo de cámara (`estatico` o `movil`) y si usa compensación de movimiento
de cámara (CMC). Se añade el perfil `patrulla` (modo `movil`). El tracker deja de tener la CMC fija en `True` y la toma
del perfil. No cambia ningún otro comportamiento del pipeline (la cercanía es la spec 057).

## Depende de
006, 016, 028.

## Archivos rectores aplicables
- ADR-017 (decisiones 2 y 3), ADR-004 (actualización 2026-10-03), docs/09-enfoque-versatil.md §2.
- docs/03-modelo-datos.md §4 (YAML de perfiles y validaciones).
- reglas-seguridad.md: sin reglas nuevas para esta spec.

## Archivos a crear/modificar
- `src/lector_placas/infrastructure/config.py`
- `src/lector_placas/adapters/tracking/botsort_tracker.py`
- `src/lector_placas/cli/composition.py`
- `config/lector.yaml`
- `tests/unit/infrastructure/test_config.py`
- `tests/unit/adapters/test_botsort_tracker.py`
- `tests/unit/cli/test_build_tracker.py` (nuevo)

No se modifica ningún otro archivo (la GUI, `gui/labels.py` y `tests/review/` quedan intactos).

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `infrastructure/config.py`
`ProfileConfig` gana dos campos, colocados **al principio** de la clase (antes de `target_fps`), en este orden y sin
valor por defecto:
- `mode: Literal["estatico", "movil"]`
- `camera_motion_compensation: bool`

`Literal` ya está importado en el módulo. No se añaden validadores de campo para ellos.

`AppConfig._validate_cross_fields` (el `model_validator(mode="after")` existente) gana una comprobación nueva que se
ejecuta **justo después** de la comprobación de `default_profile` y **antes** de la de retención: recorre
`self.profiles.items()` en orden de inserción y, para el primer perfil con `mode == "movil"` y
`camera_motion_compensation is False`, lanza
`ValueError(f"el perfil {nombre} es movil y exige camera_motion_compensation: true")`, con `nombre` la clave del perfil.

### `adapters/tracking/botsort_tracker.py`
`TrackerSettings` gana un campo **al final**, con valor por defecto: `enable_cmc: bool = True`. Se añade a la sección
`Attributes:` del docstring la línea `enable_cmc: activa la compensación de movimiento de cámara.`
`BotSortTracker.__init__` pasa `enable_cmc=settings.enable_cmc` a `BoTSORTTracker` en lugar de `enable_cmc=True`.
El docstring de la clase `BotSortTracker` pasa a ser
`"""Tracker BoT-SORT, con la CMC según `TrackerSettings.enable_cmc`, detrás del puerto `Tracker`."""`.

### `cli/composition.py`
En `build_tracker`, `TrackerSettings(...)` recibe como **argumento posicional 11 (último)**
`profile.camera_motion_compensation`.

## Comportamiento esperado

1. **YAML.** `config/lector.yaml` queda así en la sección `profiles` (solo cambia esto en el archivo):
   - Cada uno de los perfiles `parqueadero`, `calle_lenta` y `calle_rapida` añade, como **primeras dos claves** del
     perfil y en este orden, `mode: estatico` y `camera_motion_compensation: true`. Sus demás valores no cambian.
   - Se añade un cuarto perfil, **después** de `calle_rapida`, llamado `patrulla`, con exactamente estas claves y valores,
     en este orden:

     | Clave | Valor |
     |---|---|
     | `mode` | `movil` |
     | `camera_motion_compensation` | `true` |
     | `target_fps` | `30` |
     | `max_readings_per_track` | `6` |
     | `track_finalize_after_ms` | `1000` |
     | `min_readings` | `2` |
     | `confirm_threshold` | `0.90` |
     | `min_agreement` | `0.60` |
     | `min_plate_width_px` | `20` |
     | `min_sharpness` | `0.0` |
     | `max_ocr_per_frame` | `8` |
     | `vehicle_crop_margin` | `0.10` |

   - `default_profile` sigue siendo `calle_lenta`. No se toca ninguna otra sección del YAML.
2. **Validación.** Al cargar la configuración: un perfil sin `mode` o sin `camera_motion_compensation`, un `mode` distinto
   de `estatico` y `movil`, o un perfil `movil` con `camera_motion_compensation: false` hacen que `load_config` lance
   `ConfigurationError`. Un perfil `estatico` con `camera_motion_compensation: false` es válido.
3. **Tracker.** `TrackerSettings` construido con 10 argumentos (como lo hacen hoy los tests existentes) tiene
   `enable_cmc == True`. `BotSortTracker` construye la librería con el `enable_cmc` de sus ajustes.
4. **Composición.** `build_tracker(config, profile)` produce ajustes cuyo `enable_cmc` es
   `profile.camera_motion_compensation`.
5. **Nada más cambia.** Los valores efectivos de `ProcessingSettings` (`build_process_video`) no cambian: `mode` no se
   pasa al caso de uso en esta spec.

## Casos borde y manejo de errores
- El mensaje de error del perfil móvil sin CMC contiene el texto exacto
  `el perfil patrulla es movil y exige camera_motion_compensation: true` (con el nombre del perfil que falle).
- Si dos perfiles móviles incumplen la regla, el mensaje nombra solo al primero en el orden del YAML.
- Un perfil con una clave extra o con una clave faltante sigue fallando (`extra="forbid"` ya existe).
- La GUI muestra `patrulla` con el nombre generado por `profile_label` («Patrulla») porque no está en `PROFILE_LABELS`;
  no se cambia en esta spec.

## Tests de aceptación (en prosa)
Fixtures sintéticos únicamente. Los tests nuevos se **añaden** a los archivos indicados; los existentes no se modifican.

`tests/unit/infrastructure/test_config.py` (usa `base_data()` y `write()` del propio archivo):
- `test_real_config_has_four_profiles_with_modes`: `list(load_config(REAL).profiles)` es exactamente
  `["parqueadero", "calle_lenta", "calle_rapida", "patrulla"]`; los tres primeros tienen `mode == "estatico"`;
  `patrulla` tiene `mode == "movil"`; los cuatro tienen `camera_motion_compensation is True`.
- `test_patrulla_profile_values`: el perfil `patrulla` tiene `target_fps == 30`, `max_readings_per_track == 6`,
  `track_finalize_after_ms == 1000`, `min_readings == 2`, `confirm_threshold == 0.90`, `min_agreement == 0.60`,
  `min_plate_width_px == 20`, `min_sharpness == 0.0`, `max_ocr_per_frame == 8`, `vehicle_crop_margin == 0.10`.
- `test_mobile_profile_requires_cmc`: con `data["profiles"]["patrulla"]["camera_motion_compensation"] = False`,
  `load_config` lanza `ConfigurationError` y `str(error)` contiene
  `el perfil patrulla es movil y exige camera_motion_compensation: true`.
- `test_static_profile_may_disable_cmc`: con `data["profiles"]["calle_lenta"]["camera_motion_compensation"] = False`,
  `load_config` no lanza y ese perfil tiene `camera_motion_compensation is False`.
- `test_invalid_mode_raises`: con `data["profiles"]["calle_lenta"]["mode"] = "otro"`, lanza `ConfigurationError`.
- `test_missing_mode_or_cmc_raises`: dos casos independientes; borrar la clave `mode` de `calle_lenta` lanza
  `ConfigurationError`; borrar la clave `camera_motion_compensation` de `calle_lenta` lanza `ConfigurationError`.
- `test_first_offending_profile_is_named`: con `patrulla` sin CMC y un segundo perfil móvil copiado de `patrulla`
  (clave `patrulla_2`) también sin CMC, el mensaje contiene `el perfil patrulla es movil` y no contiene `patrulla_2`.

`tests/unit/adapters/test_botsort_tracker.py` (añadir `import dataclasses`, y `import pytest` si no está):
- `test_enable_cmc_defaults_to_true`: `SETTINGS.enable_cmc is True` (el `SETTINGS` existente de 10 argumentos).
- `test_enable_cmc_is_passed_to_library` (parametrizado con `True` y `False`): con
  `monkeypatch.setattr("lector_placas.adapters.tracking.botsort_tracker.BoTSORTTracker", Fake)`, donde `Fake` es una
  clase cuyo `__init__(self, **kwargs)` guarda `kwargs` en una lista del módulo de test, construir
  `BotSortTracker(dataclasses.replace(SETTINGS, enable_cmc=valor))` deja registrado un solo `kwargs` con
  `kwargs["enable_cmc"] is valor`.
- `test_tracker_keeps_id_without_cmc`: con `dataclasses.replace(SETTINGS, enable_cmc=False)`, repetir el recorrido de
  `test_moving_vehicle_keeps_id` (6 frames, `det(20 + 5 * step, 50)`, `BACKGROUND`, `step * 100` ms) da una lista de ids
  no vacía con un único valor distinto y mayor o igual a 0.

`tests/unit/cli/test_build_tracker.py` (nuevo; mismo encabezado `from __future__ import annotations` y la constante
`REAL = Path(__file__).resolve().parents[3] / "config" / "lector.yaml"`):
- `test_build_tracker_uses_profile_cmc` (parametrizado con `True` y `False`): cargar `load_config(REAL)`; crear la copia
  `profile = config.profiles["calle_lenta"].model_copy(update={"camera_motion_compensation": valor})`; con
  `monkeypatch.setattr("lector_placas.cli.composition.BotSortTracker", Fake)`, donde `Fake.__init__(self, settings)`
  guarda `settings`, llamar `composition.build_tracker(config, profile)`; el `settings` guardado es un
  `TrackerSettings` con `enable_cmc is valor` y `frame_rate == 15.0`.

## Fuera de alcance
- Usar `mode` en el pipeline, el filtro de cercanía y `min_plate_width_px` 32 (spec 057).
- Cambiar los valores de `min_plate_width_px` (siguen en 20 en los cuatro perfiles hasta la spec 057).
- Etiquetas de la GUI para `patrulla`, la web y la documentación (ya actualizada por el orquestador).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde, sin modificar tests existentes.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `uv run python -c "from pathlib import Path; from lector_placas.infrastructure.config import load_config; c = load_config(Path('config/lector.yaml')); print(list(c.profiles))"` imprime `['parqueadero', 'calle_lenta', 'calle_rapida', 'patrulla']`.
