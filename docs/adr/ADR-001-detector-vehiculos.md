# ADR-001 — Detector de vehículos

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-06, RNF-01, RNF-04, RNF-05

## Contexto
Se necesita detectar `car`, `motorcycle`, `bus`, `truck` en frames de cualquier resolución, a 1× en
una RTX 5050 (8 GB), con modelos pequeños y exportables. La propuesta original era YOLO11n/s COCO.

## Opciones evaluadas
| Opción | mAP50-95 COCO | Params | CPU ONNX (ms) | Licencia |
|---|---|---|---|---|
| YOLO11n | 39.5 | 2.6M | 56.1 | AGPL-3.0 |
| **YOLO26n** | 40.9 | 2.4M | 38.9 | AGPL-3.0 |
| YOLO11s / YOLO26s | 47.0 / 48.6 | 9.4M / 9.5M | 90.0 / 87.2 | AGPL-3.0 |
| RF-DETR nano (open-image-models) | 48.4 (384px) | 30.5M | NO VERIFICADO | Apache-2.0 |

Fuente: https://docs.ultralytics.com/models/yolo26/ , https://docs.ultralytics.com/models/yolo11/ ,
https://github.com/roboflow/rf-detr (consultadas 2026-09-24).

## Decisión
**YOLO26n preentrenado COCO** (`yolo26n.pt`, Ultralytics 8.4.162, SHA-256
`9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`), **exportado a ONNX** en el
entorno `training/detector` con cabeza end2end (salida `output0` de forma `[1, 300, 6]`:
`x1, y1, x2, y2, score, class_id` en píxeles de la entrada letterbox 640×640). Clases COCO usadas:
2=car, 3=motorcycle, 5=bus, 7=truck. En runtime se ejecuta con ONNX Runtime (ADR-009).

## Consecuencias
- (+) Más preciso y ~30 % más rápido en CPU que YOLO11n; sin NMS externo.
- (+) Exportable a LiteRT/NCNN/CoreML para el futuro.
- (−) Modelo más reciente (enero 2026): menos historial en producción. Cambiar a YOLO11n requiere
  un cambio aparte porque su exportación ONNX por defecto no es end2end (otro formato de salida).
- (−) AGPL-3.0 (ADR-008).
- COCO no distingue motocarros; un motocarro puede detectarse como `motorcycle` o `car`.
