# ADR-009 — Runtime de inferencia ONNX Runtime

- Estado: Aceptado (2026-09-24)
- Requisitos: RNF-01, RNF-03, RNF-05, RNF-08; regla "torch.load con weights_only=True"

## Contexto
Los `.pt` de Ultralytics guardan el objeto del modelo con pickle: no se pueden cargar con
`torch.load(weights_only=True)`. Además el runtime debe ser pequeño, portable y funcionar en CPU.

## Opciones evaluadas
1. PyTorch + Ultralytics en runtime: exige pickle inseguro, ~GB de dependencias.
2. **ONNX Runtime GPU** (`onnxruntime-gpu[cuda,cudnn]==1.30.0`, CUDA 13, cuDNN 9, wheels cp311–cp314).
3. TensorRT: más rápido, pero añade compilación por GPU y complejidad.

## Decisión
Toda la inferencia de runtime usa ONNX Runtime. Antes de crear sesiones se llama
`onnxruntime.preload_dlls(directory="")` (carga CUDA/cuDNN de los paquetes `nvidia-*` instalados por
los extras `cuda`/`cudnn`; documentado desde ORT 1.21). Proveedores: `["CUDAExecutionProvider",
"CPUExecutionProvider"]` con `execution_provider: cuda`, o solo CPU con `execution_provider: cpu`.
PyTorch **no** es dependencia de runtime; `torch.load` nunca se llama en `src/`.

## Consecuencias
- (+) Sin deserialización pickle en runtime; modelos verificados por SHA-256 (ADR-012).
- (+) El mismo ONNX corre en CPU y es el punto de partida para móvil.
- (−) Pre/post-procesamiento YOLO (letterbox, des-escalado) implementado por nosotros.
- (−) Hay que exportar los modelos en `training/detector` antes del primer uso del detector de vehículos.
