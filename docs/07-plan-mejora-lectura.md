# 07 - Plan para subir la tasa de confirmación sin perder precisión

Estado: propuesto (2026-09-27). Autor: Claude (diseño). Las fases que requieren código se especifican aparte
(specs 050, 051 y 054; la 052–053 añade la decisión de revisión "placa borrosa") y las implementa un subagente, como el resto del proyecto.

## 1. Diagnóstico (BD local, 121 avistamientos, 3 videos, 2026-09-26 a 2026-09-28)

Conteos agregados; ningún texto de placa salió del equipo.

| Grupo | n | Confianza consolidada |
|---|---|---|
| Confirmadas por el sistema (`reasons` vacío) | 11 (9 %) | 0,93–1,00 |
| Correctas pero dejadas `unverified` (el revisor confirmó) | 37 | mediana ≈ 0,53 |
| Incorrectas (el revisor corrigió) | 20 | mediana ≈ 0,28 |
| Rechazadas por el revisor (no placa, placa parcial) | 33 | mediana ≈ 0,12 |
| Pendientes de revisar | 20 | mediana ≈ 0,20 |

Hallazgos:

1. **Razones de `unverified`:** `low_confidence` 105, `low_agreement` 73, `unrecognized_format` 42,
   `insufficient_readings` 27, `vehicle_format_mismatch` 7. El formato no es el cuello de botella: el catálogo ya exige
   `LLLDDD` para carro/bus/camión y `LLLDD`/`LLLDDL` para moto, y ninguna lectura fuera de formato se confirmó.
2. **Tipo de error del OCR:** en las 20 corregidas hubo 46 caracteres cambiados: 29 letra→letra, 15 dígito→dígito y
   solo 2 dígito→letra. Una restricción de formato solo arregla los cruces letra↔dígito (≈ 4 %); el resto es el OCR
   confundiendo letras entre sí, sobre todo en las posiciones 0–2.
3. **El umbral no es la palanca:** las distribuciones de confianza de correctas e incorrectas se solapan. Con
   `confirm_threshold` 0,5 se confirmarían ~19 correctas más y 5 incorrectas (precisión ≈ 80 %, lejos de M-01 ≥ 98 %).
4. **Las lecturas se toman demasiado pronto (hipótesis, sin medir).** `TrackRegistry` guarda las **primeras**
   `max_readings_per_track` lecturas y después deja de leer ese track (`needs_reading`). A 15 fps, 8 lecturas son ~0,5 s
   desde que aparece una placa de ≥ 20 px (`min_plate_width_px: 20`, `min_sharpness: 0.0`). Si el vehículo se acerca a
   la cámara, se lee lejos y borroso y se ignoran los frames buenos. 43 de 121 avistamientos agotaron las 8 lecturas.
5. **Dominio:** el OCR `colombia_v1` tiene CER 3,7 % en el `test` congelado de `mix_v1` (recortes de Roboflow), pero en
   video real el acuerdo entre lecturas del mismo vehículo es bajo (mediana 0,5). Falta medir el CER real
   (`evaluate-review`).
6. **Tipo de vehículo:** 3 placas `LLLDDD` correctas quedaron en tracks clasificados como moto (`vehicle_format_mismatch`).
   Puede ser el detector de vehículos confundiendo la clase; no está comprobado.

Referencia: M-03 (recall de confirmadas) exige ≥ 75 %. Hoy el sistema confirma solo el 9 % de lo que ve.

### 1.1 Auditoría de confirmadas (2026-09-27, `lector review --status confirmed`)

13 confirmadas automáticas auditadas: 11 correctas y **2 erróneas**. La precisión estimada es 11/13 ≈ 85 %, lejos de M-01 ≥ 98 %
(la muestra es pequeña, pero dos errores en trece ya son demasiados). El sistema no solo confirma poco: también confirma mal.

Los dos errores tienen la misma causa (verificado en el código y en BD, sin textos de placa):

- Track clasificado como `motorcycle`, OCR de 6 caracteres con la última posición en dígito (patrón `LLLDDD`).
- Para una moto, el único formato compatible de longitud 6 es `co_moto` (`LLLDDL`). El consolidador prueba cada patrón:
  `correct_to_pattern` (`domain/ocr_correction.py`) convierte el dígito final en su letra de confusión (8→B, 5→S, 0→O,
  1→I). El resultado encaja en `co_moto` y se confirma.
- La confianza del carácter corregido sigue siendo la que el OCR dio **al dígito** (0,99 y 0,985; acuerdo 1,0). Nada marca
  que hubo una sustitución, así que la placa pasa todos los umbrales.
- En ambos casos el revisor devolvió el dígito: la placa real era `LLLDDD`.

Además, entre los tracks `motorcycle` con texto ya verificado por el revisor hay 10 `LLLDDD` y 8 `LLLDDL`. O el
detector de vehículos clasifica como moto muchos carros, o hay motos con placa `LLLDDD`. En cualquiera de los dos
casos, el tipo de vehículo no es lo bastante fiable como para forzar el formato. Qué vehículos son de verdad **no está
comprobado**: hay que verlos en la galería.

## 2. Fases

Orden pensado para no gastar entrenamiento antes de saber qué parte del pipeline falla. Cada fase termina con una
decisión explícita.

### Fase 0 - Asegurar los datos revisados (operador, sin código) — urgente

Los recortes cifrados se purgan a los `retention.crops_days` = 30 días. Los más antiguos son del 2026-09-26, así que
**hay que exportarlos antes del 2026-10-26**.

1. Auditar las 11 confirmadas automáticas: `lector review --status confirmed`. `export-reviewed` exporta **todo**
   `confirmed`, también lo no auditado, y una lectura mala en train contamina el OCR.
2. Revisar las 20 `unverified` pendientes: `lector review`.
3. Línea base del OCR sobre datos reales: `lector evaluate-review` (reporte en `data/eval/reports/`). Anotar `cer`,
   `exact_match_rate` y `precision_confirmed`.
4. Exportar: `lector dataset export-reviewed`. Crea `training/ocr/datasets/own/<carpeta>/` con `annotations.csv`
   (~68 recortes). No se versiona y tiene su propia retención (180 días).

**Salida:** CER real de `colombia_v1` en video y un conjunto de recortes reales guardado.

### Fase 0b - Spec 050: la corrección no reemplaza una lectura válida (código) — prioritaria (spec redactada)

Es un fallo de precisión (§1.1), no de cobertura, así que va antes que todo lo demás. Regla (ADR-007 paso 5b,
`specs/050-conflicto-correccion.md`): si el voto **sin corrección** ya es una placa válida del catálogo y la corrección
posicional llevó a otro texto, gana el texto sin corregir, que queda `unverified` con la razón nueva
`CORRECTION_CONFLICT` (más `vehicle_format_mismatch` si no encaja con el tipo de vehículo).

Se descartó "toda sustitución impide confirmar", porque rompería el caso legítimo `0BC123` → `OBC123`. También se
descartó penalizar la confianza de las posiciones corregidas, porque dependería de un factor elegido a ojo.

La BD no guarda lecturas individuales, así que los avistamientos existentes no se reconsolidan. Se valida con los
tests de la spec y, en la Fase 1 con GT, comprobando que ninguna confirmada tenga un carácter cambiado por confusión.

**Resultados de la Fase 0 (2026-09-27):** `evaluate-review` da CER real 0,1615 y exact-match 0,6522 sobre 92 lecturas
revisadas (frente a CER 0,0373 en el test congelado de `mix_v1`); `precision_confirmed` = 0,8462 (13 auditadas).
`export-reviewed` → `training/ocr/datasets/own/reviewed-20260928T003936Z` (92 recortes). Observación del revisor: la
mayoría de las placas están borrosas, lo que apoya el hallazgo 4.

### Fase 0c - Specs 052–053: decisión de revisión "placa borrosa"

Petición del usuario (2026-09-27). Separa "no es una placa" (`rejected`) de "es una placa, pero no se lee"
(`illegible`). Da la cifra que falta para la Fase 2 (cuántas placas reales se pierden por calidad de imagen) y deja
las borrosas fuera del CER y del reentrenamiento. La 052 incluye la primera migración de esquema (v1 → v2). Antes de
abrir la BD real con esa versión, conviene copiar `data/lector.db`.

### Fase 1 - Ground truth de 1 o 2 videos (operador, sin código)

Sin GT no se pueden medir M-01..M-03 ni comparar configuraciones: con la revisión solo se estima la precisión.
`data/eval/` está vacío.

1. Elegir 1 o 2 videos representativos (uno de calle; si hay motos, que aparezcan).
2. Anotarlos según docs/04 §2: `data/eval/ground_truth/<sha256>.json`, dos pasadas. Lo que ya se revisó en la
   galería ayuda a escribir los textos, pero los tiempos y las placas que el sistema no detectó se anotan viendo el video.
3. Línea base: `lector evaluate --video videos/<v> --ground-truth data/eval/ground_truth/<sha>.json --profile calle_lenta`.

Nota: `evaluate` procesa con el repositorio real, así que cada corrida añade avistamientos a la galería. Hay que
tenerlo en cuenta al revisar (o purgarlos después).

**Salida:** M-01, M-02, M-03 y M-05 de la configuración actual.

### Fase 2 - Experimentos de configuración (operador + Claude, sin código)

Se crean perfiles de prueba en `config/lector.yaml` (copias de `calle_lenta` que cambian **una** variable por perfil)
y se corre `lector evaluate` con cada uno sobre los videos con GT.

| Perfil | Cambio respecto a `calle_lenta` | Hipótesis |
|---|---|---|
| `exp_ancho40` | `min_plate_width_px: 40` | Empezar a leer cuando la placa ya es legible (hallazgo 4) |
| `exp_ancho60` | `min_plate_width_px: 60` | Ídem, más estricto; vigilar M-02 (placas que nunca llegan a 60 px) |
| `exp_lecturas16` | `max_readings_per_track: 16` | Más lecturas cubren también el tramo cercano |
| `exp_yolo` | `models.plate_detector: {backend: yolo, model_id: yolo26n-plates, input_size: 640}` | Recortes más ajustados y menos detecciones basura (las 33 rechazadas) |

- `min_sharpness` no entra en esta ronda: la nitidez no se guarda en BD, no hay distribución para elegir un umbral,
  y la escala (varianza del Laplaciano sobre 128×64) no tiene un valor de referencia verificado.
- `exp_yolo` cambia una clave global, no del perfil: se corre aparte con una config dentro de `config/`
  (p. ej. `config/exp_yolo.yaml`, usada con `lector --config`). Recordar el sesgo: `yolo26n-plates` se entrenó con `merged`.
- `confirm_threshold` y `min_agreement` **no se tocan** en esta fase (hallazgo 3).

**Regla de decisión:** se elige la variante con mayor M-03 que cumpla M-01 ≥ 98 % y no baje M-02 más de 5 puntos.
Si una variante gana, se combina con la siguiente mejor y se mide otra vez. Con pocas placas en GT, una diferencia
de 1 o 2 placas no decide nada: se anota el tamaño de muestra junto a cada métrica.

**Salida:** perfil por defecto ajustado, o la evidencia de que la configuración no basta.

### Fase 3 - Spec 051: guardar las mejores lecturas del track, no las primeras (código; spec redactada)

Solo si la Fase 2 confirma el hallazgo 4 (subir `min_plate_width_px` o `max_readings_per_track` mejora M-03).
Idea: en vez de dejar de leer al llegar a `max_readings_per_track`, `TrackRegistry` sigue leyendo y conserva las N
lecturas de mayor calidad (ancho de placa y nitidez, que ya vienen en `PlateReading`). El coste de GPU se controla con
`max_ocr_per_frame`, que ya existe. La spec fija el criterio de calidad, el desempate y los tests en prosa; se valida con la
misma batería de la Fase 2.

### Fase 4 - Reentrenar el OCR con datos del dominio (spec 054, redactada, + operador)

**Problema a resolver antes de entrenar:** `mix_dataset` reparte train/val/test ordenando los componentes por hash y
tomando los primeros `round(n × 0,2)` para test. Si se añade `--real own/<carpeta>` a la mezcla original, cambian `n` y el
orden, así que algunas muestras del `test` congelado de `mix_v1` pasan a train. Medir después sobre `mix_v1/test` daría
un CER falso (fuga).

Spec 054 (cambio acotado en `training/ocr`):
- Opción de `mix_dataset` para heredar el reparto de una mezcla anterior: las muestras reales de `mix_v1` conservan su
  split y solo las fuentes nuevas se reparten entre ellas (por vehículo, igual que hoy).
- Las fuentes nuevas generan además un `test` propio de video (`test_video`), para medir el dominio que importa.
- `evaluate_ocr` informa las dos cifras: `mix_v1/test` (comparable con todas las versiones) y `test_video`.

Datos: con ~68 recortes, un `test_video` del 20 % son ~14 placas y el IC 95 % no dice nada. Meta orientativa: **≥ 300
recortes revisados** (procesar y revisar más videos, variando hora y cámara) antes de entrenar `colombia_v2`. La cifra está
PENDIENTE DE VALIDAR con el ancho de IC que reporte `evaluate_ocr` para ese n.

Luego, con la receta actual (CLAUDE.md, sección OCR): `synthetic_plates` (si hace falta más sintético) → `mix_dataset`
con la opción nueva → `train --name colombia_v2` → `evaluate_ocr`. Aceptación según ADR-014; además, `colombia_v2` debe
mejorar el CER de `test_video` frente a `colombia_v1`. Si se acepta, se registra el hash en `config/models.yaml` y se
repite la Fase 2 con el modelo nuevo.

### Fase 5 - Mejoras menores (opcionales, al final)

- **Decodificación restringida por formato:** usar la distribución completa de probabilidades por posición en vez de la
  corrección fija O↔0, I↔1, B↔8, S↔5. Arregla solo los cruces letra↔dígito (≈ 4 % de los errores observados).
  Sin spec a propósito (2026-09-27): fast-plate-ocr 1.1.0 solo expone el máximo por posición (`char_probs =
  np.max(...)` en `core/process.py`). Tener la distribución completa exige ejecutar la sesión ONNX con el
  preprocesado privado de la librería (`_load_image_from_source`), y eso toca el adaptador, `OcrResult`,
  `PlateReading` y el consolidador. Con la spec 050 el riesgo de precisión de estos cruces ya está cubierto. Se
  reconsidera solo si la Fase 2 muestra que los cruces letra↔dígito pesan más.
- **Última letra de la moto nueva limitada a A–I:** NO VERIFICADO (el catálogo cita Res. 4923/1994 y permite `[A-Z]`).
  Se añade al catálogo solo con la fuente normativa; el efecto esperado es pequeño (1 de las 20 corregidas era moto `LLLDDL`).
- **Tipo de vehículo:** revisar en la galería los 3 casos `LLLDDD` en moto; si el detector confunde la clase, se decide si
  `vehicle_format_mismatch` debe pesar menos cuando la confianza de clase es baja.

## 3. Lo que este plan no hace

- No baja `confirm_threshold` ni `min_agreement`: sin nueva evidencia, eso cambia confirmaciones por errores.
- No envía recortes, placas ni la BD a ninguna API externa: el diagnóstico y las métricas se calculan en local.
- No cambia `docs/04-evaluacion.md`. Si alguna fase propone mover un criterio, se decide aparte (ver CLAUDE.md).
