# 04 — Evaluación y plan de datos

> Todo lo de este documento se ejecuta **localmente**. Ground truth, videos, recortes y datasets son
> datos reales o con datos personales: NO se envían a la API externa (SEG-09) y viven en
> `data/eval/` y `training/**/datasets/` (gitignored, SEG-11).

## 1. Set de evaluación

| Subconjunto | Contenido mínimo | Origen |
|---|---|---|
| `street_day` | 10 videos de 1–3 min, calle, día | Grabación propia (celular fijo y en mano) |
| `street_night` | 10 videos de 1–3 min, calle, noche con iluminación urbana | Grabación propia |
| `parking` | 10 videos de 1–3 min, parqueadero, día y noche | Grabación propia |
| `fast` | 5 videos con vehículos > 60 km/h | Grabación propia |
| `ocr_crops` | ≥ 500 recortes de placa con texto (≥ 100 de motos) | Partición val del dataset por carácter (sección 5) + recortes propios si el usuario lo aprueba (§5.2) |

Los videos de evaluación **no** se usan para entrenar (separación estricta por video, no por frame).

## 2. Formato de anotación (ground truth)

Un archivo JSON por video: `data/eval/ground_truth/<video_sha256>.json`, validado con pydantic
(`extra="forbid"`).

```json
{
  "version": 1,
  "video_sha256": "<64 hex del archivo de video>",
  "subset": "street_day",
  "camera": "fixed",
  "plates": [
    {"text": "ABC123", "vehicle_type": "car", "first_seen_ms": 1200, "last_seen_ms": 4300, "legible": true},
    {"text": "XYZ98K", "vehicle_type": "motorcycle", "first_seen_ms": 5000, "last_seen_ms": 6100, "legible": true},
    {"text": "",       "vehicle_type": "truck", "first_seen_ms": 7000, "last_seen_ms": 7900, "legible": false}
  ]
}
```

Reglas: `subset` ∈ {`street_day`, `street_night`, `parking`, `fast`}; `camera` ∈ {`fixed`, `handheld`};
`text` cumple `^[A-Z0-9]{1,10}$` si `legible = true` y es `""` si `false`; `0 ≤ first_seen_ms ≤ last_seen_ms`.
Un vehículo que pasa dos veces genera dos entradas. **Legible** = un humano puede leer los 6 (o 5)
caracteres en al menos un frame del video original.

Procedimiento de anotación: reproducir el video con un reproductor que muestre el tiempo en ms
(p. ej. `ffplay` con `-vf drawtext` de `pts`), anotar a mano en el JSON. Dos pasadas: anotar y
verificar. El `video_sha256` se obtiene con `sha256sum`.

Formato de `ocr_crops`: `data/eval/ocr_crops/annotations.csv` con columnas `image_path,plate_text`
(mismo formato que fast-plate-ocr, rutas relativas al CSV).

## 3. Métricas

| ID | Métrica | Definición | Meta (aprobada) |
|---|---|---|---|
| M-01 | Precisión de confirmadas | Avistamientos `confirmed` emparejados con una placa GT legible de igual texto / total `confirmed` | ≥ 98 % |
| M-02 | Recall total | Placas GT legibles emparejadas con algún avistamiento (`confirmed` o `unverified`) de igual texto / placas GT legibles | ≥ 90 % |
| M-03 | Recall confirmadas | Placas GT legibles emparejadas con un `confirmed` de igual texto / placas GT legibles | ≥ 75 % |
| M-04 | CER | Σ distancia de Levenshtein(pred, gt) / Σ len(gt) sobre `ocr_crops` | ≤ 3 % tras fine-tuning |
| M-05 | Velocidad | `video_duration_ms / processing_ms` (`RunStats.speed_factor`) por video ≤ 1080p30 | ≥ 1.0 en cada video |
| M-06 | VRAM pico | Máximo de `memory.used` (MiB) muestreado cada 200 ms durante la corrida menos la línea base previa | ≤ 4096 MiB |

**Emparejamiento (M-01..M-03):** un avistamiento `s` empareja con una placa GT `g` del mismo video si
`s.plate_text == g.text` y los intervalos `[first_seen_ms, last_seen_ms]` se solapan con tolerancia de
1000 ms (`s.first ≤ g.last + 1000` y `g.first ≤ s.last + 1000`). Emparejamiento uno a uno, voraz, en
orden de `first_seen_ms` del avistamiento. Los avistamientos `rejected` se ignoran; los `corrected`
cuentan con su texto corregido pero se reportan aparte (no deben existir en una evaluación limpia).

Reporte por subconjunto y global, más desglose `car` vs `motorcycle` y `fixed` vs `handheld`.

## 4. Spec del script de evaluación
Se implementa en `specs/029-evaluacion.md` (módulo `lector_placas.evaluation`):
- `lector evaluate --video <archivo> --ground-truth <json> [--profile <p>]`: procesa el video con el
  pipeline normal mientras `VramMonitor` ejecuta `nvidia-smi --query-gpu=memory.used
  --format=csv,noheader,nounits -lms 200` como subproceso (lista de argumentos, sin shell); al terminar
  calcula M-01, M-02, M-03, M-05 y M-06 para esa corrida.
- `lector evaluate-ocr --crops <annotations.csv>`: ejecuta el `PlateReader` configurado sobre los
  recortes y calcula M-04.
- Ambos escriben `data/eval/reports/report-<YYYYmmddTHHMMSSZ>.json` (0600) y un resumen en consola
  **sin texto de placa** (solo conteos y métricas).

## 5. Plan de datos para fine-tuning

### 5.1 Fuentes verificadas (2026-09-24)
| Dataset | URL | Imágenes | Anotación | Licencia | Uso |
|---|---|---|---|---|---|
| placas colombianas | https://universe.roboflow.com/licenseplates-gk27i/placas-colombianas | 1 770 | Caja de placa | CC BY 4.0 | Detector |
| Placas Colombia (usco) | https://universe.roboflow.com/usco-thj9e/placas-colombia-ixdpr | 1 106 | Caja `placa` | MIT (declarada) | Detector |
| OCR Placas Colombia | https://universe.roboflow.com/ia-xgdnt/ocr-placas-colombia-etll5 | 926 | Caja por carácter (0-9, A-Z, `ciudad`, `placa`) | CC BY 4.0 | OCR (texto derivado) |
| Placas_Motos_Carros | https://universe.roboflow.com/reimerjsuarez/placas_motos_carros | 469 | Caja `Placas` (carros y motos) | CC BY 4.0 | Detector (motos) |
| motos-placas | https://universe.roboflow.com/placas-sn7fb/motos-placas | 264 | Caja; clases H, I, Q, `motos-placas` | CC BY 4.0 | Detector (motos; origen colombiano NO VERIFICADO) |

NO VERIFICADO: duplicados entre proyectos (p. ej. `placas-colombia-detection-nano` parece copia de
usco), veracidad de licencias declaradas, proporción día/noche y de motos. Excluidos por decisión del
usuario: RodoSol-ALPR, UFPR-ALPR. Excluido por licencia ambigua: generador de `ddfulaa/deteccion_placas`
(README dice MIT, el repositorio no tiene archivo LICENSE).

Descarga: manual desde el navegador en formato "YOLOv8" (detector) / "YOLOv8" o "COCO" (caracteres),
a `training/detector/datasets/raw/<nombre>/` y `training/ocr/datasets/raw/<nombre>/`. Registrar URL,
versión y licencia en `docs/datasets/ATRIBUCIONES.md` (obligatorio por CC BY 4.0).

### 5.2 Datos propios
- Frames de videos propios **distintos** de los de evaluación: 1 de cada 15 frames muestreados con
  vehículos, anotados con cajas de placa en Label Studio 1.23.0 (Apache-2.0) ejecutado localmente
  (`uvx --python 3.13 label-studio==1.23.0`, en `localhost`). Telemetría de Label Studio: NO VERIFICADO
  cómo desactivarla; revisar su documentación antes de usarlo.
- Recortes de avistamientos `confirmed`/`corrected` revisados en la CLI: `lector dataset export-reviewed` (spec 035)
  los escribe en `training/ocr/datasets/own/reviewed-<fecha>/` (formato fast-plate-ocr, 0600, gitignored, auditado) y
  se borran a los `retention.training_days` días (180 por defecto). Decisión del usuario 2026-09-26.

### 5.3 Metas de cantidad (objetivos de trabajo, no hechos)
| Modelo | Train | Val | Composición |
|---|---|---|---|
| Detector de placas (YOLO26n, 1 clase `plate`) | ≥ 3 000 imágenes | ≥ 400 | ≥ 25 % motos, ≥ 25 % noche, ≥ 500 frames propios |
| OCR (cct-xs-v2 fine-tune) | ≥ 5 000 recortes reales + sintéticos | ≥ 500 reales | ≥ 20 % motos; sintéticos ≤ 50 % del train |

### 5.4 Etiquetado y consistencia
- Detector: una caja ajustada al borde exterior de la placa (incluye el texto de municipio/"COLOMBIA").
- OCR: `plate_text` solo con los caracteres principales (sin municipio ni "COLOMBIA"), mayúsculas,
  sin espacios ni guiones. Recortes ilegibles se descartan (no se etiquetan con texto parcial).
- Deduplicación por hash perceptual antes de dividir en train/val (spec 031).
- Partición: en datasets públicos se respeta su partición (train → train; valid/test → val) y se eliminan de
  val las imágenes casi duplicadas de alguna de train (dHash con distancia de Hamming ≤ 4). En datos propios,
  partición por video (nunca por frame).
