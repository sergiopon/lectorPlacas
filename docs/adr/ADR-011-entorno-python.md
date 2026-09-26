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
3. OpenCV único: `opencv-python==4.14.0.94` y en `[tool.uv] override-dependencies` la entrada
   `"opencv-python-headless; sys_platform == 'never'"` para que nunca se instale el paquete headless.
   (La versión 5.0.0.93 se evita hasta verificar compatibilidad de las librerías.)
4. En `training/ocr`, override `"protobuf>=6.31.1,<8"` para `tf2onnx` (resolución a verificar con
   `uv lock` en spec 032; si no resuelve o falla el smoke test, se detiene y se revisa este ADR).

## Consecuencias
- (+) Runtime pequeño y reproducible; entrenamiento aislado con sus conflictos.
- (−) Tres lockfiles que mantener.
- (−) Verificación de GPU (compute capability 12.0) en spec 000 y en spec 030.
