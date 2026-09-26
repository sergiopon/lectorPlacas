# ADR-003 — OCR de placas

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-09, RF-17, RNF-01, RNF-04; M-04 (CER ≤ 3 %)

## Contexto
Propuesta original: fast-plate-ocr principal, PaddleOCR alternativa, VLM pequeño como fallback.
Hallazgos verificados:
- fast-plate-ocr 1.1.0 (MIT): modelos `cct-xs-v2-global` / `cct-s-v2-global`; su lista
  `plate_regions` (65 países) **no incluye Colombia** (de LatAm solo Argentina, Brasil, México).
- Configuración `cct_xs_v2_global_plate_config.yaml`: `max_plate_slots: 10`,
  alfabeto `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_`, `pad_char: '_'`, entrada 64×128,
  `image_color_mode: rgb`, `keep_aspect_ratio: false`.
- API: `LicensePlateRecognizer(onnx_model_path=..., plate_config_path=..., providers=[...])`,
  `run(list_of_rgb_arrays, return_confidence=True) -> list[PlatePrediction]` con `plate: str` y
  `char_probs: np.ndarray` (una probabilidad por carácter decodificado).
- Existen pesos Keras publicados (`cct_xs_v2_global.keras`) para fine-tuning con
  `fast-plate-ocr train --weights-path`.
- Las motos colombianas tienen **una sola fila** de caracteres (Res. 4923/1994), compatible con el modelo.

## Opciones evaluadas
1. **fast-plate-ocr cct-xs-v2 + fine-tuning colombiano.** 0,32 ms/placa (xs-v1, RTX 3090 TensorRT,
   dato del autor), ONNX, exportable a TFLite/CoreML.
2. PaddleOCR 3.7 (Apache-2.0): OCR genérico de texto, no especializado en placas; stack Paddle adicional.
3. VLM (Qwen3-VL-2B Apache-2.0 GGUF ≈ 2–2,5 GB): latencia alta, compite por VRAM y puede
   **alucinar placas plausibles**, lo que contradice "precisión primero".

## Decisión
- Lector único v1: **`cct-xs-v2-global`** (ONNX SHA-256
  `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`; config SHA-256
  `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6`) como baseline y
  **fine-tuning obligatorio** con placas colombianas (spec 032).
- PaddleOCR y VLM **fuera de v1**: las lecturas dudosas ya van a revisión humana (CLI). El puerto
  `PlateReader` permite añadirlos después sin tocar el orquestador.

## Consecuencias
- (+) Un solo runtime (ONNX Runtime), VRAM mínima, 1× alcanzable.
- (−) El baseline leerá peor las placas colombianas hasta el fine-tuning; la votación, la
  corrección posicional y los umbrales mitigan confirmaciones erróneas.
- El entorno de entrenamiento OCR (TensorFlow/Keras) se aísla en `training/ocr` (ADR-011). El fine-tuning
  usa el backend torch de Keras; la **exportación a ONNX del modelo ajustado** se hace en un subproceso con
  `KERAS_BACKEND=tensorflow` (tf2onnx) sobre una copia del `.keras` sin configuración de compilación, porque
  `torch.onnx` no soporta el kernel de `PatchExtractor` con lote dinámico (detalle en spec 032, paso 5.6).
  El modelo exportado conserva el contrato del adaptador de la spec 017: entrada `input` uint8
  `[batch, 64, 128, 3]` y salida `plate` `[batch, 10, 37]`.
