# ADR-011 — Entorno: Python 3.13, uv, PyTorch cu130 aislado

- Estado: Aceptado (2026-09-24)
- Requisitos: RNF-06, RNF-14

## Contexto
Fedora 44 trae Python 3.14. La propuesta original pedía PyTorch cu128 para Blackwell (sm_120).

Hechos verificados (2026-09-24):
- PyTorch retiró los builds cu128 desde 2.12. PyTorch 2.14.0 ofrece cu126, cu130, cu132; cu126 no
  incluye sm_120. Existen wheels `torch-2.14.0+cu130-cp313-cp313-manylinux_2_28_x86_64` y
  `torchvision-0.29.0+cu130-cp313-...`.
- `tensorflow` 2.21.0 (requerido por `fast-plate-ocr[train]`) solo publica wheels cp310–cp313.
- `tf2onnx` 1.16.1 exige `protobuf~=3.20` y `tensorflow` 2.21 exige `protobuf>=6.31.1`.
- `fast-plate-ocr` y `open-image-models` dependen de `opencv-python-headless`; `trackers` y
  `ultralytics` dependen de `opencv-python`. Ambos instalan el módulo `cv2` y se pisan.

## Decisión
1. **Python 3.13** fijado (`.python-version` = `3.13`) y gestionado con **uv 0.12.19**.
2. Tres proyectos uv independientes:
   - raíz (runtime + dev): sin torch; ONNX Runtime GPU.
   - `training/detector`: `torch==2.14.0`, `torchvision==0.29.0` desde el índice explícito
     `https://download.pytorch.org/whl/cu130`, `ultralytics==8.4.162`.
   - `training/ocr`: `fast-plate-ocr[train]==1.1.0` con `KERAS_BACKEND=torch` y torch cu130.
     El fine-tuning corre con `KERAS_BACKEND=torch`, pero la **exportación a ONNX** se hace en un
     subproceso con `KERAS_BACKEND=tensorflow` (tf2onnx) y `CUDA_VISIBLE_DEVICES=""`, por dos hechos
     medidos al entrenar: `torch.onnx` no soporta el kernel de `PatchExtractor` con lote dinámico,
     y el `compile_config` del `.keras` entrenado con torch referencia
     `keras.src.backend.torch.optimizers.torch_adamw`, que aborta el proceso al convivir con
     TensorFlow. El subproceso oculta la GPU porque TensorFlow 2.21 no encuentra sus librerías CUDA
     y grappler falla al intentar usarla.
3. OpenCV único: `opencv-python==4.14.0.94` y en `[tool.uv] override-dependencies` la entrada
   `"opencv-python-headless; sys_platform == 'never'"` para que nunca se instale el paquete headless.
   (La versión 5.0.0.93 se evita hasta verificar compatibilidad de las librerías.)
4. En `training/ocr`, override `"protobuf>=6.31.1,<8"` para `tf2onnx` (verificado al entrenar:
   `uv lock` resuelve y el smoke test de exportación a ONNX termina en 0).

## Consecuencias
- (+) Runtime pequeño y reproducible; entrenamiento aislado con sus conflictos.
- (−) Tres lockfiles que mantener.
- (−) Verificación de GPU (compute capability 12.0) al configurar el entorno y al entrenar el detector.
