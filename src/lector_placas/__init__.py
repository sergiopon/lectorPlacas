"""lectorPlacas: ALPR local para placas colombianas."""

from __future__ import annotations

import os

# SEG-20: el hilo de telemetría nativo de ONNX Runtime no lo frena `block_network()`. La
# variable DEBE fijarse antes de que cualquier módulo importe `onnxruntime` (fijarla
# después no surte efecto).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

__version__: str = "0.1.0"
