# 051 - Aplicación: cada track conserva sus mejores lecturas, no las primeras

## Objetivo
Hoy `TrackRegistry` guarda las **primeras** `max_readings_per_track` lecturas de un track y después `needs_reading`
devuelve `False`: el track no se vuelve a leer. Con `calle_lenta` (15 fps, 8 lecturas) eso cubre ~0,5 s desde que la
placa alcanza `min_plate_width_px` (20 px). En video de calle el vehículo suele acercarse, así que se leen los frames
lejanos y borrosos y se ignoran los cercanos. El revisor observó que la mayoría de los recortes están borrosos, y 43
de 121 avistamientos agotaron las 8 lecturas (docs/07 §1, hallazgo 4). El CER real es 0,1615, frente a 0,0373 en el
test congelado.

Cambio: el track se sigue leyendo mientras está activo, y cuando ya tiene `max_readings_per_track` lecturas, una nueva
lectura **reemplaza a la peor** si es estrictamente mejor. "Mejor" significa placa más ancha en el frame y, a igual
ancho, más nítida. `max_readings_per_track` pasa a significar "cuántas lecturas se votan", no "cuántas se hacen".

## Depende de
023, 024.

## Archivos rectores aplicables
- docs/02-contratos.md §6 (`TrackRegistry`, ya actualizado con `is_full` y la nueva semántica).
- docs/adr/ADR-006-muestreo-perfiles.md (enmienda 2026-09-27: coste de OCR).
- ARQUITECTURA.md: `application` solo importa `domain` y numpy; límites de §6.
- reglas-seguridad.md SEG-05 (sin texto de placa en mensajes ni logs).

## Archivos a crear/modificar
- `src/lector_placas/application/track_registry.py`
- `src/lector_placas/application/process_video.py` (solo `_collect_candidates`)
- `tests/unit/application/test_track_registry.py`
- `tests/unit/application/test_process_video.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
- `TrackRegistry.needs_reading(track_id) -> bool`: mantiene la firma. Ahora devuelve `True` si y solo si el track
  está en el registro (activo), tenga o no el máximo de lecturas.
- Nuevo `TrackRegistry.is_full(track_id) -> bool`: `True` si el track está en el registro y tiene ya
  `max_readings_per_track` lecturas; `False` si no existe o tiene menos.
- `TrackRegistry.add_reading(reading, crop) -> None`: mantiene la firma. Ya no lanza error por track lleno. Sigue
  lanzando `InvalidEntityError` si el track no existe.
- Sin cambios en `FinalizedTrack`, `ProcessingSettings`, la configuración YAML ni el esquema de BD.

## Comportamiento esperado
1. **Calidad de una lectura** (clave de comparación, auxiliar privado del módulo): la tupla
   `(ancho de reading.plate_box, reading.quality_score)`, donde el ancho es `x2 - x1` en coordenadas del frame y
   `quality_score` es la nitidez (varianza del Laplaciano) que ya calcula el pipeline. Se compara como tupla: primero
   el ancho y, a igual ancho, la nitidez. **No** se usa la confianza del OCR: favorecería lecturas erróneas muy seguras,
   como las de docs/07 §1.1.
2. `add_reading` con el track por debajo del máximo: añade la lectura (como hoy).
3. `add_reading` con el track lleno:
   - La *peor* lectura guardada es la de menor clave `(ancho, nitidez, timestamp_ms)`. Entre empates de calidad, la
     peor es la más antigua.
   - Si la calidad `(ancho, nitidez)` de la nueva es **estrictamente mayor** que la de la peor, la peor se descarta y
     la nueva entra. Si no, la nueva se descarta.
   - Consecuencia deseada: con calidad constante, el resultado es idéntico al actual (se quedan las primeras).
4. **Mejor recorte:** se evalúa con todas las lecturas que llegan a `add_reading` de un track existente, se guarden o
   no, con el mismo criterio y la misma puntuación de hoy (`quality_score * mean_confidence`, reemplazo solo si es
   estrictamente mayor).
5. **Orden de salida:** `FinalizedTrack.readings` sale ordenado por `(timestamp_ms, frame_index)` ascendente, sin
   importar el orden en que entraron o se reemplazaron. Así el resultado es determinista para el consolidador.
6. **Prioridad en `ProcessVideo._collect_candidates`:** los tracks elegibles (`needs_reading`) se ordenan primero los
   que **no** están llenos (`is_full` falso) y, dentro de cada grupo, por área de la caja del vehículo descendente
   (como hoy). Luego se toman los primeros `max_ocr_per_frame`. Así un track lleno no le quita turno de OCR a uno que
   aún no tiene lecturas suficientes.
7. El resto de `ProcessVideo` no cambia. `min_plate_width_px` y `min_sharpness` siguen filtrando antes de leer.

**Coste:** cada track activo se procesa (detección de placa y OCR) en cada frame muestreado, dentro del tope de
`max_ocr_per_frame`. Antes dejaba de procesarse tras `max_readings_per_track` lecturas. El operador comprueba M-05
(velocidad ≥ 1,0) en la Fase 2 de docs/07; esta spec no añade un límite nuevo.

## Casos borde y manejo de errores
- Track desconocido: `needs_reading` y `is_full` devuelven `False`; `add_reading` lanza `InvalidEntityError` con el
  `track_id` en el mensaje (como hoy, sin texto de placa).
- `max_readings_per_track = 1`: el track guarda una sola lectura y la cambia por cualquier otra estrictamente mejor.
- Un track finalizado sale del registro. Si el mismo `track_id` reaparece, es un track nuevo (comportamiento de la
  spec 023, que no cambia).

## Tests de aceptación

### `tests/unit/application/test_track_registry.py`
Se usan los auxiliares del archivo. Hace falta poder fijar el ancho de la caja de placa: se añade un parámetro de ancho
al auxiliar de lectura (caja `(0, 0, ancho, 10)`) sin cambiar su valor por defecto (10).

Caso existente que cambia de expectativa (la vieja era el límite que esta spec elimina):

1. `test_reading_limit_and_best_crop`: `TrackRegistry(2)`, dos lecturas (confianza 0,5 y nitidez 10 en t=0;
   confianza 0,9 y nitidez 10 en t=100). Tras ellas, `needs_reading(1)` sigue siendo `True` y `is_full(1)` es `True`.
   Una tercera lectura con nitidez 5 en t=200 **no lanza error** y se descarta. Las lecturas finales tienen
   timestamps `[0, 100]` y el mejor recorte es el de la segunda (valor 2).

Casos nuevos:

2. `test_wider_plate_replaces_worst_reading`: `TrackRegistry(2)`, lecturas de ancho 20 (t=0) y 40 (t=100), misma
   nitidez; una tercera de ancho 60 (t=200) entra y desplaza a la de ancho 20. Timestamps finales `[100, 200]`.
3. `test_sharpness_breaks_width_tie`: mismo ancho; nitidez 5 (t=0) y 10 (t=100); una tercera con nitidez 7 (t=200)
   desplaza a la de nitidez 5. Timestamps finales `[100, 200]`.
4. `test_equal_quality_keeps_earliest_readings`: `TrackRegistry(2)` y tres lecturas de igual ancho y nitidez (t=0,
   100, 200): se quedan `[0, 100]`.
5. `test_readings_are_returned_in_time_order`: `TrackRegistry(2)`, lecturas en t=300 (ancho 30) y t=100 (ancho 20),
   y después t=200 (ancho 40), que desplaza a la de t=100. Las lecturas finales salen ordenadas `[200, 300]`.
6. `test_best_crop_can_come_from_discarded_reading`: `TrackRegistry(1)`: lectura de ancho 40, nitidez 1, confianza
   0,5 (recorte 1); después una de ancho 20, nitidez 50, confianza 0,9 (recorte 2), que se descarta por ser más
   estrecha, pero tiene mayor `quality_score * mean_confidence`. La lectura final es la de ancho 40 y el mejor
   recorte es el 2.
7. `test_is_full_for_unknown_and_partial_tracks`: `is_full` es `False` para un track desconocido y para uno con menos
   lecturas que el máximo, y `True` al alcanzarlo.

`test_unknown_track_and_needs_reading` y los demás casos existentes pasan sin cambios, igual que
`tests/review/test_review_023.py`.

### `tests/unit/application/test_process_video.py`
Se reutiliza `build(...)` y los fakes del archivo.

Caso existente que cambia de expectativa:

8. `test_happy_path_confirms_plate`: con 10 frames y `max_readings_per_track = 8`, el lector se llama ahora **10**
   veces (antes 8), porque el track se sigue leyendo. `num_readings` sigue siendo 8 y el resto de aserciones no cambia.

Casos nuevos:

9. `test_later_wider_plates_replace_early_readings`: un detector de placas guionizado devuelve, en llamadas
   sucesivas, cajas de ancho creciente (todas ≥ `min_plate_width_px`), y un lector guionizado devuelve `"AAA111"` en
   las primeras llamadas y `"ABC123"` en las últimas. Con `max_readings_per_track = 2` y 4 frames (anchos crecientes;
   `"AAA111"` en las llamadas 1–2 y `"ABC123"` en las 3–4), el avistamiento guardado tiene `ocr_text == "ABC123"` y
   `num_readings == 2`.
10. `test_full_track_yields_ocr_turn_to_unfilled_track`: dos tracks por frame (uno grande y otro pequeño, como el
    `TwoTrackTracker` de `tests/review/test_review_024.py`, que puede copiarse al archivo), `max_ocr_per_frame = 1`,
    `max_readings_per_track = 1` y 2 frames. En el frame 0 se lee el grande y en el frame 1 el pequeño, así que al final
    hay dos avistamientos, uno por track.

`tests/review/test_review_024.py` (vehículo más grande primero con `max_ocr_per_frame = 1`) pasa sin cambios.

## Fuera de alcance
- Cambiar valores de perfiles (`max_readings_per_track`, `min_plate_width_px`, `min_sharpness`): lo decide la Fase 2 de docs/07.
- Limitar el coste de OCR por track con un parámetro nuevo.
- Usar la confianza del OCR para elegir lecturas.
- Cambiar el consolidador (spec 050).

## Definition of Done
- `uv run pytest tests/unit/application tests/review tests/architecture` pasa.
- `uv run pytest` completo pasa (tests de GUI con `QT_QPA_PLATFORM=offscreen`).
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- Solo cambian los cuatro archivos listados.
