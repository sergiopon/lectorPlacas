# ADR-002 — Detector de placas

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-07, RNF-05; riesgo "poco dato colombiano"

## Contexto
No existen pesos de detector de placas colombianas. Entrenar uno requiere etiquetar datos (Fase 5).
Se necesita un detector usable desde el primer día para construir y medir el pipeline completo.

## Opciones evaluadas
1. Esperar al fine-tuning de YOLO26n: bloquea todo el pipeline hasta tener datos.
2. `morsetechlab/yolov11-license-plate-detection` (AGPL-3.0): su autor advierte que el dataset de
   entrenamiento mezcla train/test (métricas infladas).
3. **`open-image-models` 0.6.0 (MIT)**: detectores ONNX `yolo-v9-t-{256,384,416,512,640}` y
   `yolo-v9-s-608`, clase única `License Plate`, API `YoloV9Detector(model_path, class_labels, *,
   conf_thresh, providers)` y `predict(bgr_image) -> list[DetectionResult]` con coordenadas en el
   espacio de la imagen de entrada. Dataset de entrenamiento: NO VERIFICADO. Licencia específica de
   los pesos: NO VERIFICADO (el repositorio es MIT).

## Decisión
- **v1 (baseline):** `yolo-v9-t-384-license-plate-end2end` de open-image-models
  (archivo `yolo-v9-t-384-license-plates-end2end.onnx`, SHA-256
  `888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8`, 7 771 218 bytes).
  Se ejecuta **sobre el recorte del vehículo** (ADR-013), por eso 384 px de entrada basta.
- **v1.1:** YOLO26n fine-tuneado con placas colombianas, exportado a ONNX end2end con
  una clase `plate`. Ambos implementan el puerto `PlateDetector`; se elige por configuración
  (`models.plate_detector.backend: open_image_models | yolo`).

## Consecuencias
- (+) Pipeline funcional sin entrenamiento; métricas baseline medibles.
- (+) La interfaz no cambia al pasar al modelo propio.
- (−) Desempeño desconocido con placas colombianas y motos; se mide en Fase 5.
- (−) El tamaño 384 es provisional; alternativas del mismo paquete se configuran sin código.
