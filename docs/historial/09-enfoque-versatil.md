# 09 - Enfoque versátil: solo placas cercanas y legibles, con cámara estática o móvil

Estado: propuesta de diseño (2026-10-03). Autor: Claude Opus (diseño). Continúa `docs/historial/07-plan-mejora-lectura.md` y
`docs/historial/08-plan-legibilidad-y-web.md` y **reordena** las specs que este último dejó sin redactar (056–071).
Nada de este documento es código: cada decisión se implementa en la spec indicada en el §5, con el ciclo habitual.

Decisiones del usuario (2026-10-03) que motivan este documento:
1. Solo interesan las placas **legibles y cercanas**. Las lejanas no se leen, no se muestran y no se revisan.
2. El sistema es **versátil**, con dos modos disponibles: **cámara estática** (parqueadero, entrada, calle) y
   **cámara móvil en vehículo** (patrulla y similares).
3. Toda spec debe poder implementarla una IA que solo programe: este documento toma ahora las decisiones, con cifras.

Choque con un requisito vigente: **RF-04** (`docs/00-requisitos.md`) dice que el sistema procesa cámara fija o en
movimiento "sin exigir declarar cuál es el caso". Con esta decisión el modo **se declara** al elegir el perfil. RF-04
se reescribe (§4.5).

---

## 0. Resumen de decisiones

| # | Decisión | Valor | Spec |
|---|---|---|---|
| D1 | "Cercana" se mide como el **ancho de la caja de la placa en el frame**, con un mínimo efectivo que combina un piso absoluto y una fracción del lado mayor del frame | `ceil(max(min_plate_width_px, near_min_width_frac × max(ancho, alto del frame)))`; por defecto `max(32 px, 0,025 × lado mayor)` → 48 px en 1080p y 32 px en 720p | 057 |
| D2 | Lo lejano se descarta **antes** de detectar la placa y de leerla: ROI, tamaño del vehículo, ancho de la placa y placa cortada por el borde | Orden fijo en el §1.4 | 057 |
| D3 | Lo ilegible que pasa el filtro de cercanía se oculta **después**, con el filtro de legibilidad de docs/historial/08 §2, entrenado y medido solo sobre la población cercana | Criterio de docs/historial/08 §2.4 restringido a la población cercana | 062–064 |
| D4 | El modo es un **campo del perfil** (`mode`, con valor `estatico` o `movil`), no una bifurcación del pipeline. Un solo código | Perfiles actuales → `estatico`; perfil nuevo `patrulla` → `movil` | 056 |
| D5 | La compensación de movimiento de cámara (CMC) pasa a ser un campo **por perfil**. `movil` la exige; en `estatico` se deja encendida hasta que el experimento E3 demuestre que apagarla no fragmenta tracks | `camera_motion_compensation: true` en los cuatro perfiles al inicio | 056 |
| D6 | Duplicados de la misma placa en una corrida: no se borran, se **marcan** (`duplicate_of`) y salen de la vista por defecto | Mismo texto en la misma corrida, con hueco ≤ `dedup_window_ms` = 30 000 ms | 059 (columna), 061 (lógica) |
| D7 | Parada temprana por track: se mantiene la 060, redefinida como "el track lleno que ya se confirmaría deja de leerse" | `early_stop: true` en los cuatro perfiles | 060 |
| D8 | Fuente de video: **solo archivos** en esta etapa. Sin cámara en vivo, sin GPS y sin hora absoluta | — | Ninguna (fuera de alcance, §3.5–3.6) |
| D9 | Privacidad del modo móvil: regla nueva **SEG-29** (sin ubicación, sin listas de búsqueda ni alertas, solo se guarda el recorte de la placa) y **ADR-017** | — | Redacta Claude antes de la 056 |
| D10 | La evaluación cuenta solo las placas cercanas: el ground truth gana `max_plate_width_px` y la cámara `vehicle_mounted` | Formato GT versión 2 | 058 |

---

## 1. Definición operativa de "cercana y legible"

### 1.1 Datos de partida (medidos hoy, en local, sin texto de placa)

Fuentes: `data/exports/sightings-20260928T032425Z.csv` (1 113 avistamientos revisados, de 7 corridas), cabeceras PNG de
`training/ocr/datasets/own/reviewed-20260928T032456Z/` (329 recortes legibles) y `ffprobe` de `videos/`. Solo se
calcularon conteos y percentiles; ningún texto de placa salió del equipo ni se imprimió.

| Hecho | Cifra |
|---|---|
| Estados finales | 241 confirmadas + 88 corregidas = **329 legibles**; **422 borrosas**; **362 no-placa** |
| Ancho del mejor recorte de las legibles (px del frame) | p05 = 31, p10 = 32, p25 = 46, **mediana 59**, p75 = 79, p95 = 138 |
| Legibles con mejor recorte < 30 / < 40 / < 50 / < 60 px | 4,6 % / 17,0 % / 34,3 % / 50,8 % |
| Entrada del OCR (`cct_xs_v2_global_plate_config.yaml`) | 128 × 64 px, `keep_aspect_ratio: false`: toda placa de menos de 128 px de ancho se **amplía** |
| Duplicados entre legibles: mismo texto en la misma corrida | 40 grupos, **57 avistamientos sobrantes (17 % de las legibles)**; 56 de 57 con hueco ≤ 18,6 s (33 se solapan en el tiempo); 1 con hueco de 910 s |
| `num_readings ≤ 1` como regla de ocultar | Oculta 1,5 % de las legibles y 19,5 % de las inservibles |
| Videos disponibles | 6 reales a 1920×1080 (14 s a 79 s, de 23,7 a 58,7 fps de media) y `videoLargo.mp4` a 1280×720, 59,94 fps, 17 min (la corrida 23) |
| Tipo de vehículo en los revisados | Carros: 229 legibles de 690 (33 %). Motos: 61 de 327 (19 %) |

Limitaciones de estos datos:
- El "mejor recorte" se elige por `quality_score × mean_confidence` y no tiene por qué ser el más ancho que alcanzó el
  track. Su ancho es una **cota inferior** del ancho máximo de la placa. Las cifras de pérdida de la tabla son
  pesimistas.
- El ancho de los recortes de las borrosas y las no-placas no se conoce todavía: `export-legibility` (spec 055) está
  implementado pero **no se ha ejecutado** (no existe `training/legibility/datasets/own/`).
- El reparto de legibles por resolución no se puede separar con los datos exportados: 208 de las 329 legibles son de
  la corrida 23 (720p).

### 1.2 Medida de cercanía (D1)

La distancia no se puede medir directamente con una sola cámara. Su sustituto es el **tamaño aparente de la placa**,
que además es lo que decide si el OCR puede leerla. Se usan dos números:

1. **Piso absoluto de legibilidad** `min_plate_width_px` (campo existente): por debajo, el OCR amplía un recorte sin
   información. Valor nuevo: **32 px** en los cuatro perfiles (hoy 20). Con los datos del §1.1 corta como mucho el 5–10 %
   de las legibles actuales (p05 = 31, p10 = 32).
2. **Fracción de cercanía** `near_min_width_frac` (campo nuevo): ancho mínimo de la placa como fracción del **lado mayor**
   del frame ya rotado. Se usa el lado mayor y no el ancho porque, con el mismo sensor, la resolución angular depende del
   lado mayor: un video vertical de 1080×1920 y uno horizontal de 1920×1080 ven la placa con los mismos píxeles a la misma
   distancia. Valor: **0,025** en los cuatro perfiles.

**Ancho mínimo efectivo** de un frame: `ceil(max(min_plate_width_px, near_min_width_frac × max(frame.width, frame.height)))`.

| Resolución | Lado mayor | Mínimo efectivo con los valores por defecto |
|---|---|---|
| 1280×720 | 1280 | max(32; 32,0) = **32 px** |
| 1920×1080 | 1920 | max(32; 48,0) = **48 px** |
| 3840×2160 | 3840 | max(32; 96,0) = **96 px** |

Distancia orientativa (**NO VERIFICADO**: depende del ancho real de la placa y del campo de visión de la cámara). Con una
placa de carro de 33 cm de ancho (dimensión PENDIENTE DE VALIDAR en la normativa, como ya señala docs/historial/08 §3 punto 5) y un
campo de visión horizontal de 70° (valor típico de cámara principal de celular, NO VERIFICADO para las cámaras usadas),
la distancia es aproximadamente 0,33 m / (2 × fracción × tan 35°). Con 0,025 sale **≈ 9 m**; con 0,020, ≈ 12 m; con
0,015, ≈ 16 m. Una placa de moto, más pequeña, necesita estar más cerca para dar el mismo ancho.

Por qué 0,025 y no otro valor: es la cifra que corresponde a "unos 9 m", un alcance razonable de "cercana" tanto en una
entrada de parqueadero como para el carro de delante o del carril de al lado en una patrulla. Coste conocido: en 1080p
deja fuera las placas de menos de 48 px, y hasta el 34 % de las legibles actuales tiene el mejor recorte por debajo de
50 px (cota pesimista, §1.1). Eso es coherente con la decisión del usuario ("las lejanas no interesan"), pero la frontera
exacta es una **decisión de producto** que el usuario confirma con el experimento E1 (§6), que puede bajarla a 0,020.
Hasta entonces el valor de la spec es 0,025.

`near_min_width_frac` admite **0,0**, que desactiva la fracción y deja solo el piso absoluto (útil para reproducir el
comportamiento anterior en una comparación).

### 1.3 Zona de interés (ROI)

Campo nuevo por perfil `roi`: rectángulo en coordenadas normalizadas `[x1, y1, x2, y2]` sobre el frame ya rotado, con
`0 ≤ x1 < x2 ≤ 1` y `0 ≤ y1 < y2 ≤ 1`. Valor por defecto en los cuatro perfiles: **`[0.0, 0.0, 1.0, 1.0]`** (todo el
frame). Un vehículo está dentro si el **centro de su caja** (`(x1+x2)/2`, `(y1+y2)/2` en píxeles) cumple
`roi.x1 × ancho ≤ cx ≤ roi.x2 × ancho` y `roi.y1 × alto ≤ cy ≤ roi.y2 × alto` (bordes incluidos).

Uso previsto, que no cambia los valores por defecto: en estático, excluir una calle de fondo; en móvil, excluir el capó
del propio vehículo (franja inferior). El operador lo ajusta por instalación copiando el perfil en `config/lector.yaml`.
La ROI es un rectángulo y no un polígono: un polígono exige elegir y probar un algoritmo de punto en polígono y no hay
un caso medido que lo pida.

### 1.4 Qué se descarta ANTES de leer (D2), en este orden

Para cada frame muestreado, después de `Tracker.update` y `TrackRegistry.observe` (sin cambios), en
`ProcessVideo._collect_candidates` y `_plate_candidate`:

1. **ROI del vehículo.** Se descartan los tracks cuyo centro de caja queda fuera de `roi`. Coste: nulo.
2. **Tamaño del vehículo.** Se descartan los tracks cuya caja de vehículo (sin el margen `vehicle_crop_margin`) tiene un
   ancho menor que `mínimo efectivo / max_plate_vehicle_ratio`. Campo nuevo por perfil `max_plate_vehicle_ratio` = **0,5**
   en los cuatro: una placa nunca ocupa más de la mitad del ancho de la caja de su vehículo (carro ≈ 0,19 y moto ≈ 0,3
   con dimensiones NO VERIFICADAS; 0,5 deja margen para cajas recortadas u ocluidas). En 1080p el vehículo debe medir
   ≥ 96 px. Evita gastar el detector de placas en vehículos lejanos. Lo valida E2.
3. **Prioridad y tope.** Solo con los tracks que pasan 1 y 2 se aplica el orden de la spec 051 (primero los no llenos,
   luego por área descendente) y el tope `max_ocr_per_frame`. Así un vehículo lejano nunca le quita un turno de OCR a
   uno cercano. Hoy el tope se aplica antes de cualquier filtro de tamaño.
4. **Detección de placa** en el recorte del vehículo (sin cambios, ADR-013) y elección de la de mayor confianza.
5. **Placa cortada por el borde.** Se descarta la placa si su caja, ya trasladada al frame, queda a menos de **2 px**
   de cualquier borde del frame (`x1 < 2`, `y1 < 2`, `x2 > ancho − 2` o `y2 > alto − 2`). Una placa cortada da lecturas
   parciales que el consolidador puede confundir con un formato corto (`LLLDD`). Constante `FRAME_EDGE_MARGIN_PX = 2`.
6. **Ancho de la placa** ≥ mínimo efectivo (§1.2). Sustituye a la comparación actual con `min_plate_width_px`.
7. **Nitidez** ≥ `min_sharpness` (sin cambios). Se queda en **0,0** en los cuatro perfiles hasta que E8 dé un umbral con
   datos: la escala de la varianza del Laplaciano sobre 128×64 no tiene un valor de referencia y hoy la nitidez no se
   guarda (lo hará la 059).

Al final de cada corrida, `ProcessVideo` registra en el log una línea de conteos (sin texto de placa) con los descartes
de cada paso: `cercania run_id=<n> fuera_roi=<n> vehiculo_pequeno=<n> sin_placa=<n> placa_en_borde=<n>
placa_estrecha=<n> borrosa=<n>`. Son los números con los que se miden E1 y E2. No se añaden columnas a `runs`.

Un track que nunca pasa los siete pasos no tiene lecturas, **no se persiste** y solo suma en
`RunStats.tracks_without_reading` (comportamiento actual, ARQUITECTURA §3 paso 6). Así se cumple "las lejanas no se
muestran ni se revisan".

### 1.5 Qué se descarta DESPUÉS de leer

Sobre la población que ya pasó el filtro de cercanía:
1. **Consolidación** (ADR-007, sin cambios): lo dudoso queda `unverified` con sus razones.
2. **Duplicados** (D6, specs 059 y 061): al cerrar la corrida, de cada grupo de avistamientos con el mismo `plate_text`
   en la misma corrida y huecos ≤ `dedup_window_ms`, se conserva uno y los demás se marcan con `duplicate_of`. No se
   borran. Ver §3.4.
3. **Filtro de legibilidad** (docs/historial/08 §2, specs 062–064): añade `PREDICTED_ILLEGIBLE` o `PREDICTED_NOT_PLATE`. Nunca
   confirma ni borra; lo oculto va a la pestaña "Ocultas por baja calidad (N)".

La vista por defecto muestra: avistamientos no duplicados y sin razón `PREDICTED_*`.

### 1.6 Una placa que empieza lejos y se acerca (o al revés)

- El **track** nace en cuanto el detector de vehículos y BoT-SORT lo confirman (sin cambios). Se observa y vota tipo
  de vehículo desde el primer frame, aunque esté lejos.
- La **lectura** empieza en el primer frame muestreado en que la placa pasa los pasos 1–7 del §1.4. Antes no se gasta
  detector de placas (si falla 1 o 2) ni OCR.
- Mientras sigue cerca, la spec 051 conserva las `max_readings_per_track` lecturas de mayor (ancho, nitidez): al
  acercarse, las lecturas más anchas sustituyen a las primeras.
- Si se aleja (el carro que adelanta a la patrulla, el que sale del parqueadero), deja de pasar el paso 6 y no se lee
  más. Las lecturas cercanas ya guardadas se conservan.
- Con `early_stop` (D7, spec 060), un track lleno cuyas lecturas ya se confirmarían deja de leerse aunque siga cerca.
- El track se finaliza como hoy, `track_finalize_after_ms` después de su última observación.

---

## 2. Modelo de modos y perfiles (D4, D5)

### 2.1 Principio

Un solo pipeline. El modo no activa ramas de código: es una **etiqueta declarada** en el perfil que (a) obliga a
ciertos valores mediante la validación de la configuración, (b) agrupa los perfiles en la interfaz y (c) separa los
resultados de la evaluación. Todo lo que cambia el comportamiento son campos del perfil con un valor explícito.

### 2.2 Campos nuevos en `profiles.<nombre>` de `config/lector.yaml`

Todos son **obligatorios** (el modelo es `extra="forbid"` y sin valores por defecto implícitos, como los actuales). Cada
campo lo añade la spec que lo usa; el YAML del repo y los fixtures de test se actualizan en esa misma spec.

| Campo | Tipo | Rango válido | Mensaje de validación (exacto) | Spec |
|---|---|---|---|---|
| `mode` | `Literal["estatico", "movil"]` | — | el de pydantic para `Literal` | 056 |
| `camera_motion_compensation` | `bool` | si `mode == "movil"`, debe ser `true` | `el perfil <nombre> es movil y exige camera_motion_compensation: true` | 056 |
| `near_min_width_frac` | `float` | [0,0, 0,2] | `near_min_width_frac debe estar en [0, 0.2]: <valor>` | 057 |
| `max_plate_vehicle_ratio` | `float` | (0,0, 1,0] | `max_plate_vehicle_ratio debe estar en (0, 1]: <valor>` | 057 |
| `roi` | `tuple[float, float, float, float]` | cada valor en [0, 1], `x1 < x2`, `y1 < y2` | `roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1` | 057 |
| `early_stop` | `bool` | — | — | 060 |
| `dedup_window_ms` | `int` | [0, 600 000]; 0 desactiva la marca de duplicados | `dedup_window_ms debe estar en [0, 600000]: <valor>` | 061 |

`camera_motion_compensation` sustituye al `enable_cmc=True` fijo de `adapters/tracking/botsort_tracker.py`:
`TrackerSettings` gana `enable_cmc: bool`, que `build_tracker` toma del perfil (ya recibe el perfil para `frame_rate`).
`cmc_method` y `cmc_downscale` siguen globales en `tracker:`.

### 2.3 Valores de cada perfil

Los tres perfiles existentes pasan a `mode: estatico` sin cambiar ninguno de sus valores actuales salvo
`min_plate_width_px` (20 → 32). Se añade un cuarto perfil, **`patrulla`**, `mode: movil`. `default_profile` sigue siendo
`calle_lenta`.

| Campo | `parqueadero` | `calle_lenta` | `calle_rapida` | `patrulla` (nuevo) |
|---|---|---|---|---|
| `mode` | estatico | estatico | estatico | **movil** |
| `target_fps` | 10 | 15 | 30 | 30 |
| `max_readings_per_track` | 8 | 8 | 6 | 6 |
| `track_finalize_after_ms` | 3000 | 2000 | 1000 | 1000 |
| `min_readings` | 3 | 3 | 2 | 2 |
| `confirm_threshold` | 0,90 | 0,90 | 0,90 | 0,90 |
| `min_agreement` | 0,60 | 0,60 | 0,60 | 0,60 |
| `min_plate_width_px` | **32** | **32** | **32** | 32 |
| `near_min_width_frac` | 0,025 | 0,025 | 0,025 | 0,025 |
| `max_plate_vehicle_ratio` | 0,5 | 0,5 | 0,5 | 0,5 |
| `roi` | [0, 0, 1, 1] | [0, 0, 1, 1] | [0, 0, 1, 1] | [0, 0, 1, 1] |
| `min_sharpness` | 0,0 | 0,0 | 0,0 | 0,0 |
| `max_ocr_per_frame` | 8 | 8 | 8 | 8 |
| `vehicle_crop_margin` | 0,10 | 0,10 | 0,10 | 0,10 |
| `camera_motion_compensation` | true | true | true | true |
| `early_stop` | true | true | true | true |
| `dedup_window_ms` | 30000 | 30000 | 30000 | 30000 |

Justificación de `patrulla`:
- `target_fps` 30, `max_readings_per_track` 6, `min_readings` 2: el tiempo que una placa pasa cerca de una patrulla es
  corto (vehículo en sentido contrario o adelantado), igual que en `calle_rapida`. Más frames muestreados dan más
  candidatos nítidos entre los que la spec 051 elige.
- `track_finalize_after_ms` 1000: coincide con el tiempo que BoT-SORT conserva un track perdido. Verificado en
  `trackers` 2.6.0 (`trackers/core/botsort/tracker.py`): `lost_track_buffer` se expresa "en frames a 30 FPS" y
  `maximum_time_without_update = lost_track_buffer / 30.0`, así que el `lost_track_buffer: 30` global equivale a 1,0 s
  con cualquier `target_fps`. Esperar más en el registro solo retrasa la finalización: un ID perdido no vuelve.
- CMC obligatoria (§3.1).
- Hoy `patrulla` y `calle_rapida` difieren solo en el modo. Es intencionado: el modo móvil se calibra con su propio
  material (E6) y solo entonces se separan los valores, en la configuración, sin código.

Por qué no se apaga ya la CMC en estático: no hay ninguna medida de lo que cuesta ni de lo que fragmenta. E3 lo mide en
los videos de cámara fija; si pasa, se cambia a `false` en los tres perfiles estáticos con un cambio de configuración
anotado en `specs/README.md`.

### 2.4 Lo que NO cambia por modo

`tracker:` (salvo la CMC), `models:`, `consolidation:`, el catálogo de formatos, la retención y la consolidación por
voto. La política de duplicados es la misma en los dos modos (§3.4).

---

## 3. Diferencias técnicas del modo móvil

### 3.1 Movimiento propio de la cámara

Verificado en el código: `BotSortTracker` construye `trackers.BoTSORTTracker` con `enable_cmc=True`,
`cmc_method` `sparseOptFlow` y `cmc_downscale` 2 (`config/lector.yaml` → `tracker:`), y le pasa el frame completo en cada
`update`. La biblioteca estima una homografía entre frames enmascarando las cajas detectadas y corrige las predicciones
del filtro de Kalman. Es justo lo que necesita una cámara en movimiento y ya funciona; el único cambio es poder apagarla
en estático (D5). No se cambia `cmc_method`: no hay datos para preferir otro, y `ecc` o `sift` son más caros.

Riesgo propio del móvil: la homografía global supone una escena dominante. Con la cámara girando en una esquina o con el
parabrisas sucio, puede fallar y fragmentar tracks. Los fragmentos se cubren con la marca de duplicados (§3.4); la tasa
se mide en E6.

### 3.2 Desenfoque de movimiento

En móvil la velocidad relativa es la suma de las dos velocidades en sentido contrario y casi nula en el mismo sentido.
Decisiones:
- No se lee en sentido contrario a velocidad alta de forma especial: si la placa sale borrosa, el filtro de
  legibilidad la oculta. No hay modo de "solo mismo sentido".
- La clave de calidad de la spec 051 (ancho y después nitidez) no cambia: con el filtro de cercanía todas las lecturas
  ya son anchas. Si E8 muestra que en móvil la nitidez discrimina mejor que el ancho entre lecturas legibles e
  ilegibles del mismo track, se propone otra clave en una spec aparte. PENDIENTE DE VALIDAR.
- La mitigación principal es de captura (§3.7): obturación rápida y 30 fps o más.

### 3.3 Vehículos a distinta velocidad

El muestreo por tiempo (ADR-006) y la finalización por tiempo ya son independientes de la velocidad. A 30 fps muestreados,
un vehículo que está 0,5 s dentro de la zona cercana da unos 15 frames candidatos; con `min_readings` 2 basta con que
dos sean legibles.

### 3.4 Duplicados (D6)

Medido (§1.1): el 17 % de las legibles ya son duplicados dentro de su corrida, muchos solapados en el tiempo (dos tracks
a la vez con la misma placa: un vehículo con dos cajas, o la placa de un vehículo vista en el recorte con margen del de
al lado). En móvil se espera más, por la fragmentación. Decisión:
- **Criterio:** mismo `plate_text` exacto, misma corrida, estado `confirmed` o `unverified`, y los avistamientos
  ordenados por `first_seen_ms` forman una cadena en la que cada uno empieza como mucho `dedup_window_ms` después de que
  termine el anterior (`siguiente.first_seen_ms − anterior.last_seen_ms ≤ dedup_window_ms`; los solapes dan valores
  negativos y cuentan).
- **Ventana:** 30 000 ms en los cuatro perfiles. Cubre 56 de los 57 duplicados medidos (máximo 18,6 s) y deja fuera la
  vuelta a los 910 s, que es razonable tratar como otro paso.
- **A quién se conserva:** en cada grupo, el de estado `confirmed` si lo hay; luego el de mayor `confidence`; a igualdad,
  el de menor `sighting_id`. Los demás reciben `duplicate_of = sighting_id` del conservado.
- **Cuándo:** una sola vez al terminar la corrida (después de `pop_all` y antes de `finish_run`), solo con los
  avistamientos de esa corrida. Una corrida cancelada o fallida no marca duplicados.
- Solo texto **exacto**. Dos lecturas de la misma placa con un carácter distinto no se agrupan: agruparlas exigiría un
  umbral de distancia sin datos y podría esconder una placa distinta. PENDIENTE DE VALIDAR con E6.
- Un duplicado no se borra ni cambia de estado: sale de la vista por defecto. La decisión de revisión sobre el
  conservado no se propaga a los duplicados.

### 3.5 GPS y hora absoluta: fuera de alcance

No se leen ni se guardan ubicación, ruta ni hora de grabación. Motivos:
- Una placa con ubicación y hora absoluta es un registro de movimientos de una persona: sube el riesgo y cambia el
  análisis legal (§4.6). El proyecto se define como uso personal y académico de un solo operador (`docs/00` §1).
- Leer la ubicación exige analizar metadatos del contenedor que varían por fabricante. Que los videos actuales los
  traigan está NO VERIFICADO, y no se va a verificar porque no se usarán.
- Los avistamientos ya llevan el tiempo relativo al video (`first_seen_ms`), suficiente para revisar.
SEG-29 lo convierte en regla (§4.6).

### 3.6 Fuente de video: se mantienen solo archivos

Recomendación: **solo archivos de video** en todas las specs de este documento. Motivos:
1. La velocidad medida es **0,85×** del tiempo real (docs/historial/08 §1). En vivo, por debajo de 1× se acumulan frames y hay que
   decidir qué se descarta; eso es otro diseño.
2. Una cámara IP o RTSP necesita red, y `block_network()` (SEG-20) la prohíbe en runtime. Abrir esa excepción exige su
   propio ADR y su revisión de seguridad.
3. Las cámaras de patrulla o de tablero suelen grabar a archivo y exportar después (NO VERIFICADO para un modelo
   concreto): el modo móvil es útil sin vivo.
4. El puerto `VideoSource` ya aísla la fuente (RF-34): añadir una cámara local (V4L2) más adelante no reescribe el
   pipeline.
Condición para reabrirlo: M-05 ≥ 1,2× medido en 1080p con `patrulla` y con `calle_lenta` (E4), más un ADR propio.

### 3.7 Hardware y captura

- **Proceso:** en el PC de referencia (RTX 5050, 8 GB), después de grabar. Procesar dentro del vehículo queda fuera de
  alcance (exige vivo y otro hardware; rendimiento NO VERIFICADO).
- **Cámara (guía para el README, sin código):** 1080p o más, 30 fps o más, fija en un soporte (trípode en estático;
  ventosa o soporte de tablero en móvil, mirando hacia delante), sin zoom digital, sin estabilización electrónica si la
  cámara permite apagarla (recorta y reescala el frame) y con la obturación más rápida que permita la luz. Los valores
  concretos de obturación están PENDIENTES DE VALIDAR con E9.
- **Coste por modo:** `patrulla` muestrea a 30 fps, como `calle_rapida`. El filtro de cercanía reduce las llamadas al
  detector de placas y al OCR, pero no las del detector de vehículos ni la CMC, que corren en cada frame muestreado.
  M-05 en `patrulla` está PENDIENTE DE VALIDAR (E4).

---

## 4. Impacto en lo ya existente

### 4.1 Renumeración de las specs de docs/historial/08 (aún no redactadas)

El orden numérico es el orden de implementación (`specs/README.md`), así que las specs nuevas desplazan a las del plan
08. Ninguna está redactada, así que renumerar no rompe nada.

| Número en docs/historial/08 | Contenido | Número nuevo | Cambio de alcance |
|---|---|---|---|
| — | Modos de cámara | **056** | Nueva |
| — | Filtro de cercanía | **057** | Nueva |
| — | Evaluación con cercanía (GT v2) | **058** | Nueva |
| 056 | Características de calidad, migración v2 → v3 | **059** | Añade `duplicate_of` a la migración y `frame_width`/`frame_height`/`plate_width_px` al CSV de legibilidad |
| 060 | Parada temprana por track | **060** | Se redefine (D7, §4.3) |
| — | Duplicados en la corrida | **061** | Nueva |
| 057 | Modelo de legibilidad (entrenamiento) | **062** | Se entrena y se mide solo sobre la población cercana (§4.2) |
| 058 | Filtro de legibilidad en el pipeline | **063** | Sin cambios de alcance |
| 059 | Vista "solo legibles" | **064** | También oculta duplicados |
| 061 | Tipo de vehículo por la forma de la placa | **065** | Sin cambios; sigue bloqueada por la normativa |
| 062–069 | Web | **066–073** | 066 (API de lectura): `/api/profiles` devuelve `mode`; `Run.profile` pasa a `string` |
| 070–071 | Docker | **074–075** | Sin cambios |

Hay que actualizar `docs/historial/08` (§2.3, §3, §4.7, §4.8, §5) y `specs.md` con los números nuevos, y el **Anexo A** (prompt de
Figma Make) **antes** de que el usuario lo use: el selector de escenario agrupa las tarjetas por modo y añade "Patrulla
(cámara en vehículo)"; `Run.profile` deja de ser una unión de tres nombres y pasa a `string`, con `mode:
"estatico" | "movil"` aparte; `Sighting` gana `duplicates: number` (cuántos avistamientos apuntan a él).

### 4.2 Métrica de aceptación del filtro de legibilidad (docs/historial/08 §2.4)

Lo lejano ya no llega a la revisión, así que el filtro se entrena y se mide **solo sobre lo que pasaría el filtro de
cercanía**. Si se midiera sobre los 1 113 actuales, se premiaría al filtro por esconder placas lejanas que en el sistema
nuevo ni siquiera existen.
- **Población cercana** de un ejemplo del dataset 055: `plate_width_px ≥ ceil(max(32, 0,025 × max(frame_width,
  frame_height)))`. Como el ancho del mejor recorte es una cota inferior del ancho máximo del track, la población queda
  algo recortada por abajo; se acepta y se anota en el informe.
- Criterio sin cambios en sus cifras, aplicado a esa población y al split de prueba por video: legibles escondidas
  ≤ 5 % (condición dura), borrosas y no-placas ocultadas ≥ 60 % (objetivo informado), IC por bootstrap por vehículo.
- **Mínimo de datos para entrenar (062):** ≥ 100 ejemplos de cada clase en la población cercana, repartidos en ≥ 4
  grupos de video. Si no se alcanza, la 062 no se ejecuta y se revisan más videos con el sistema nuevo.
- **Línea base obligatoria:** el modelo debe superar a la regla "`num_readings ≤ 1` es inservible" (hoy: 1,5 % de
  legibles escondidas y 19,5 % de inservibles ocultas, sobre los 1 113). Si no la supera, la 063 implementa esa regla en
  lugar del modelo.
- El criterio de docs/historial/08 §7 ("≥ 60 % menos inservibles en la vista por defecto, ≤ 5 % de legibles escondidas") pasa a
  medirse con el sistema completo (cercanía, duplicados y legibilidad) contra una corrida de referencia anterior a la 057
  sobre los mismos videos, y "legibles" significa "legibles y cercanas".

### 4.3 Spec 060 (parada temprana)

Se mantiene, con esta definición: si el perfil tiene `early_stop: true`, después de cada `add_reading` en un track
**lleno** (`is_full`), `ProcessVideo` consolida sus lecturas actuales con el tipo de vehículo dominante en ese momento;
si el resultado es `CONFIRMED`, el registro marca el track como **resuelto** y `needs_reading` devuelve `False` para
él hasta que se finalice. Se sigue observando (última aparición y votos de tipo). Al finalizar se consolida como hoy.
Con el filtro de cercanía su beneficio es mayor en estático (un carro detenido frente a la cámara se leería en cada
frame durante minutos) que en móvil. Riesgo: una lectura confirmada mal deja de recibir lecturas que podrían
contradecirla. E5 lo vigila.

### 4.4 Spec 061 del plan 08 (tipo de vehículo por la forma de la placa), ahora 065

No depende del modo. El filtro de cercanía la favorece (placas más grandes, proporción mejor medida). Sigue bloqueada
hasta verificar las dimensiones oficiales de las placas de carro y de moto en la normativa (Res. 4923/1994 y Ficha Técnica
MT 001, PENDIENTE DE VALIDAR). Las mismas dimensiones afinarían la distancia orientativa del §1.2.

**Dimensiones aportadas por el usuario (2026-10-04, a partir de dos planos; NO contrastadas con la Res. 4923/1994 ni la
Ficha MT 001):** placa de carro 33,0 × 16,0 cm (proporción ancho/alto 2,06); placa de moto, la que lleva "COLOMBIA",
23,5 × 10,5 cm (proporción 2,24). Las proporciones difieren solo un 8,5 %, y la perspectiva (placa girada respecto de la
cámara) acorta el ancho aparente y baja la proporción: una moto vista de lado parece una placa de carro, pero una placa
de carro nunca parece más ancha de lo que es. Por eso la proporción solo sirve como indicio de moto (valor alto), no como
prueba de carro. **Decisión del usuario (2026-10-04): la 065 se descarta**, porque la diferencia es mínima.

### 4.5 Documentos rectores y de requisitos que cambian (los redacta Claude, antes de la 056)

- `docs/00-requisitos.md`: RF-03 añade el perfil `patrulla`. RF-04 pasa a: "El sistema procesa video de cámara fija o
  de cámara montada en un vehículo; el operador declara el modo al elegir el perfil". RF-08 se mantiene. Nuevo RF-37: "Solo
  se leen, guardan y muestran placas cuyo ancho alcanza el mínimo de cercanía del perfil". Riesgo nuevo: el umbral de
  cercanía descarta placas legibles más lejanas (aceptado por el usuario el 2026-10-03).
- `ARQUITECTURA.md` §3 (pasos del §1.4) y §8 (modos y campos), `docs/02-contratos.md` (`ProcessingSettings`,
  `TrackerSettings.enable_cmc`, puertos de duplicados), `docs/03-modelo-datos.md` (campos del perfil, esquema v3),
  `CONTEXT.md`.
- **ADR-017 "Modos de cámara y filtro de cercanía"** (nuevo; el 016 queda reservado para la web): D1, D2, D4–D8, con
  las alternativas descartadas (bifurcar el pipeline por modo, medir la cercanía por la altura del vehículo, ROI
  poligonal, borrar duplicados, fuente en vivo).
- Enmiendas: ADR-004 (CMC por perfil), ADR-006 (campos nuevos y `patrulla`; `min_plate_width_px` 32).
- `docs/04-evaluacion.md`: lo cambia la 058 (§5), con la aprobación previa de un revisor Opus independiente y del
  usuario, porque altera la definición de M-02 y M-03.

### 4.6 Privacidad y seguridad del modo móvil

Lo que cambia de verdad con una patrulla:
- **Finalidad y responsable.** El proyecto se diseñó para uso personal y académico, con un solo operador (`docs/00` §1).
  Que una entidad lo opere (policía, vigilancia privada) cambia el responsable del tratamiento, la finalidad y la base
  legal. La Ley 1581 de 2012 rige el tratamiento de datos personales (las placas lo son, como ya asume
  `reglas-seguridad.md`), pero su artículo 2 excluye algunas bases de datos (entre ellas, según su texto, las de
  seguridad y defensa nacional). Si el uso policial cabe en alguna excepción, y si aplican otras normas (por ejemplo la
  Ley 1843 de 2017 sobre sistemas de detección electrónica de infracciones), está **PENDIENTE DE VALIDAR** con la
  normativa oficial y asesoría jurídica. El README debe decirlo así y no presentar el modo móvil como apto para uso
  policial.
- **Más terceros captados:** placas de vehículos estacionados en zonas residenciales que no pasan por un punto de control
  elegido. La tabla `plates` acumula `first_seen_at`/`last_seen_at` entre corridas; con ubicación sería un historial de
  movimientos. Por eso no se guarda ubicación (§3.5).
- **Cotejo con listas (hotlists) y alertas:** es el uso típico de un ALPR policial y queda **fuera de alcance**. Exige
  datos de terceros, probablemente integración con bases externas (RUNT ya está excluido en `docs/00` §7) y análisis legal.

**SEG-29 (nueva), para `reglas-seguridad.md` §1:** "El sistema NO DEBE leer, derivar ni guardar ubicación (GPS,
metadatos de ubicación del contenedor de video, nombres de calle) ni la hora absoluta de grabación de un avistamiento.
Solo DEBE guardarse el recorte de la placa: nunca el del vehículo ni el frame completo. NO DEBE implementarse cotejo
con listas de placas buscadas, alertas ni consulta a bases externas sin un ADR propio y la validación legal del uso
previsto. La retención (SEG-03) es la misma en los dos modos." Se añade al checklist del §8: "¿Se lee o guarda algún
metadato de ubicación u hora de grabación? ¿Se persiste algún recorte que no sea el de la placa?".

### 4.7 Operación urgente, sin código (no depende de este documento)

1. **Ejecutar ya `lector dataset export-legibility`.** La 055 está implementada, pero no hay ninguna exportación.
   Es la copia de seguridad del dataset antes de que caduquen los recortes (2026-12-25). Repetirla después de integrar
   la 059, que añade las columnas de ancho de placa y tamaño del frame; si la 059 no llega antes del 2026-12-25, la
   062 usará `crop_width` y la resolución de cada corrida, que el operador apunta a mano desde el historial.
2. **Clasificar los 7 videos de `videos/`** como cámara fija, en mano o en vehículo. No consta en ningún documento y no
   se puede deducir sin verlos. Es la entrada de E3 y E6.

---

## 5. Lista ordenada de specs (para que Claude las redacte)

Antes de la 056: ADR-017, SEG-29 y los cambios de rectores y requisitos del §4.5 (los redacta Claude).

| # | Título | Depende de | Implementa |
|---|---|---|---|
| **056** | Modos de cámara en la configuración: campos `mode` y `camera_motion_compensation` por perfil, validación "movil exige CMC", perfil `patrulla`, `TrackerSettings.enable_cmc` tomado del perfil | 006, 016, 028 | D4, D5, §2.2–2.3 |
| **057** | Filtro de cercanía antes de leer: `near_min_width_frac`, `max_plate_vehicle_ratio`, `roi`, mínimo efectivo, placa en borde (`FRAME_EDGE_MARGIN_PX` = 2), filtros de ROI y de vehículo antes del tope `max_ocr_per_frame`, `min_plate_width_px` 32 en los perfiles, línea de log `cercania …` | 051, 056 | D1, D2, §1.2–1.4 |
| **058** | Evaluación con cercanía: ground truth versión 2 (`max_plate_width_px` por placa, `camera` añade `vehicle_mounted`, `subset` añade `patrol`); `lector evaluate` excluye de M-02/M-03 las placas por debajo del mínimo efectivo del perfil usado y reporta el desglose por `camera`; la versión 1 se sigue leyendo (sin `max_plate_width_px`, toda placa cuenta como cercana) | 029, 057 | D10, §6 E6–E7 |
| **059** | Características de calidad por avistamiento y migración de esquema v2 → v3 (receta de la 052): columnas `plate_width_px`, `plate_height_px`, `sharpness` y `contrast` del mejor recorte, más `duplicate_of` (nula, referencia a `sightings`); el CSV de `export-legibility` añade `plate_width_px`, `frame_width`, `frame_height` | 052, 055, 057 | §4.2, D6 (columna) |
| **060** | Parada temprana por track: campo `early_stop`; un track lleno cuya consolidación actual sale `CONFIRMED` deja de leerse | 051, 056 | D7, §4.3 |
| **061** | Duplicados de la misma placa en la corrida: campo `dedup_window_ms`; marca `duplicate_of` al terminar la corrida con el criterio del §3.4; `SightingBrowser` excluye los duplicados por defecto y la GUI lo hereda sin cambios visuales | 041, 059 | D6, §3.4 |
| **062** | Modelo de legibilidad (entrenamiento, `training/legibility`), solo con la población cercana, mínimo de datos y línea base del §4.2 | 055, 059 | D3, §4.2 |
| **063** | Filtro de legibilidad en el pipeline (`PREDICTED_ILLEGIBLE` / `PREDICTED_NOT_PLATE`) | 062 | D3 |
| **064** | Vista "solo legibles": oculta `PREDICTED_*` y duplicados; pestaña "Ocultas por baja calidad (N)"; `evaluate-review` informa las legibles ocultas | 061, 063, 048 | §1.5 |
| **065** | Tipo de vehículo por la forma de la placa (bloqueada: normativa PENDIENTE DE VALIDAR) | 013, 015, 057 | §4.4 |
| **066–073** | Web (antes 062–069). La 066 expone `mode` en `/api/profiles` y `duplicates` en `/api/sightings` | Las de docs/historial/08, renumeradas | §4.1 |
| **074–075** | Docker (antes 070–071) | Las de docs/historial/08, renumeradas | — |

Pueden ir en paralelo: 058 con 059; 060 con 061 (tocan `track_registry.py`/`process_video.py` la 060 y la capa de
persistencia la 061; si ambas tocan `process_video.py`, primero la 060). La web (066 en adelante) puede empezar en
paralelo desde la 056, como prevé docs/historial/08 §5.

---

## 6. Riesgos y experimentos de validación

Todos se ejecutan en local; los resultados se publican solo como conteos y métricas (SEG-09).

| ID | Pregunta | Material | Procedimiento | Criterio numérico | Cuándo |
|---|---|---|---|---|---|
| E1 | ¿0,025 es la frontera de "cercana" que quiere el usuario? | `export-legibility` (ya posible) | Tomar los recortes legibles de 1080p y agruparlos por ancho: [38, 48) y [48, 58) px. Enseñar al usuario 20 de cada grupo, en local | Si el usuario considera "cercanas" ≥ 15 de 20 del grupo [38, 48), `near_min_width_frac` baja a 0,020; si no, se queda en 0,025. Informar además el % de legibles, borrosas y no-placas por debajo de cada umbral, por tipo de vehículo | Ahora |
| E2 | ¿El filtro de vehículo (ratio 0,5) descarta placas que habrían pasado? | 6 videos 1080p + `videoLargo` | Procesar cada video con `max_plate_vehicle_ratio` 0,5 y con 1,0 | Avistamientos con `plate_width_px` ≥ mínimo efectivo: diferencia ≤ 1 por video. Si no, el ratio sube a 0,7 y se repite | Tras 059 |
| E3 | ¿Se puede apagar la CMC en estático? | Videos clasificados como cámara fija (§4.7) | Procesar con `camera_motion_compensation` true y false | Con false: `tracks_total` sin aumentar más de un 5 %, duplicados marcados sin aumentar más de un 5 % y velocidad mejor. Si cumple todo, false en los tres perfiles estáticos | Tras 061 |
| E4 | M-05 por perfil | Los 6 videos 1080p | `lector process` con `calle_lenta`, `calle_rapida` y `patrulla` | ≥ 1,0× en cada video. Si `patrulla` no llega, su `target_fps` baja a 20 y se repite; si aún no llega, se informa | Tras 057 y tras 060 |
| E5 | ¿La parada temprana cambia resultados? | Mismos videos | Procesar con `early_stop` true y false | Confirmadas: mismo conjunto de textos (diferencia ≤ 1 por video) y ninguna confirmada nueva que el revisor corrija; velocidad mejor | Tras 060 |
| E6 | ¿El modo móvil funciona? | **Material nuevo:** ≥ 3 videos de 3–5 min desde un vehículo, cámara en soporte mirando hacia delante, 1080p a 30 fps o más, de día, con ≥ 50 placas cercanas en total; GT versión 2 | `lector evaluate --profile patrulla` | M-01 ≥ 98 %, M-02 ≥ 90 % y M-03 ≥ 75 % sobre placas cercanas y legibles; avistamientos no duplicados por placa GT cercana ≤ 1,2; M-05 ≥ 1,0×. Hasta cumplirlo, el README dice "modo móvil no validado" | Tras 058 y 061 |
| E7 | Línea base estática con verdad | Tramo de 3–5 min de un video fijo existente (docs/historial/07 Fase 1), anotado con GT versión 2 | `lector evaluate --profile calle_lenta`, antes (sin 057) y después de la 057 | Informar M-01..M-03 y M-05 con su n. La 057 no puede bajar M-02 sobre placas cercanas más de 5 puntos | Tras 058 |
| E8 | Umbral de nitidez | Avistamientos de la población cercana revisados tras la 059 (≥ 300) | Distribución de `sharpness` por clase | `min_sharpness` = el mayor valor que deja fuera ≤ 2 % de las legibles; se adopta solo si oculta ≥ 20 % de las borrosas. Lo aprueba un revisor Opus | Tras 059 |
| E9 | Guía de captura | Material nuevo: misma escena grabada con dos velocidades de obturación | Procesar y revisar | Informar el % de legibles de cada grabación; la guía del README recomienda la mejor | Cuando haya material |

Riesgos sin experimento propio:
- **Motos:** su placa es más pequeña, así que el mismo umbral en píxeles exige que estén más cerca. Hoy solo el 19 % de
  las motos revisadas son legibles (33 % en carros). E1 informa la pérdida por tipo de vehículo; si la de motos supera en
  más de 15 puntos a la de carros, se propone un factor por tipo en una spec aparte.
- **Sesgo del dataset de legibilidad:** se recogió sin filtro de cercanía y con otra mezcla de videos. La 062 lo
  compensa restringiendo la población (§4.2); si no hay datos suficientes, se espera a revisar corridas nuevas.
- **Placa del vehículo vecino:** los duplicados solapados del §1.1 indican que el recorte con margen puede contener otra
  placa. Si E3 o E6 lo confirman, se estudia bajar `vehicle_crop_margin`; no se cambia sin datos.

---

## 7. Reglas de redacción para implementadores sin criterio

Se aplican las 10 reglas de `specs/README.md` ("Reglas de redacción de las specs"). Además, para las specs de este plan:

1. **Campos de configuración:** cada campo nuevo lleva nombre, tipo, rango, mensaje de validación exacto, valor en cada
   uno de los cuatro perfiles de `config/lector.yaml` y valor en los fixtures de test. Ningún campo tiene valor por
   defecto implícito en el código.
2. **Unidades y coordenadas:** píxeles del frame **ya rotado** (salida de PyAV); tiempos en milisegundos de PTS;
   fracciones en [0, 1]. Para cada fórmula, el redondeo (`ceil`, `floor`) y si las comparaciones incluyen el borde.
3. **Posición exacta en el flujo:** cada filtro dice antes y después de qué paso existente se ejecuta (§1.4) y qué
   devuelve cuando descarta (`None`, lista vacía o contador).
4. **Contadores y logs:** literal completo de cada línea de log nueva, con nombres de clave y orden, y comprobación de que
   no lleva texto de placa.
5. **Tests que cambian de expectativa:** lista nominal de los tests existentes cuyo resultado cambia (por ejemplo, los
   que usan placas de 20–31 px con `min_plate_width_px` 20) y su nuevo resultado.
6. **Datos de test con cifras:** tamaño de frame, cajas de vehículo y de placa en píxeles, ROI y resultado esperado
   (pasa o se descarta y en qué paso), incluidos los casos en el borde exacto de cada umbral.
7. **Migraciones:** versión de origen y de destino, DDL completo, valores de las filas existentes (`NULL` para todas las
   columnas nuevas) y prueba de migración sobre una BD v2 sintética.
8. **Empates y orden:** desempates de toda selección (conservado de un grupo de duplicados, prioridad de OCR) y orden de
   recorrido.
9. **Comandos del operador:** si una spec deja un paso manual (copiar un hash, ejecutar una exportación), el comando
   exacto y la salida esperada, fuera del Definition of Done del implementador.
10. **Lo PENDIENTE no entra en la spec:** un valor que dependa de E1–E9 se escribe con el valor vigente de este documento,
    y el cambio posterior se hace en la configuración, con nota en `specs/README.md`.

---

## 8. Pendientes que bloquean

| Pendiente | Bloquea | Cómo se resuelve |
|---|---|---|
| Ejecutar `export-legibility` con datos reales | 062 (y el dataset entero si se pasa el 2026-12-25) | Operador, ya (§4.7) |
| Clasificar los videos existentes (fijo, en mano o en vehículo) | E3, E6, E7 | Operador (§4.7) |
| Frontera de "cercana" (0,025 o 0,020) | Nada (la 057 sale con 0,025); ajuste posterior por configuración | E1 |
| Material grabado desde un vehículo con GT | Declarar validado el modo móvil | E6 |
| Base legal del uso por una entidad (Ley 1581 art. 2, Ley 1843 de 2017 u otras) | Publicar el modo móvil como apto para ese uso; cualquier cotejo con listas | Asesoría jurídica y normativa oficial: PENDIENTE DE VALIDAR |
| Dimensiones oficiales de las placas | 065 y la distancia orientativa del §1.2 | Aportadas por el usuario (§4.4); falta contrastarlas con la Res. 4923/1994 y la Ficha MT 001, y medir la proporción en datos reales |
| Cambio de M-02/M-03 a "placas cercanas" en docs/04 | 058 | Revisor Opus independiente y aprobación del usuario |
