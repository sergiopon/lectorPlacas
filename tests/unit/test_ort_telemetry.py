"""El paquete desactiva la telemetría nativa de ONNX Runtime antes de importarlo (SEG-20)."""

from __future__ import annotations

import os
import subprocess
import sys

_CODE = "import os, lector_placas; print(os.environ.get('ORT_DISABLE_TELEMETRY'))"


def _run(extra_env: dict[str, str]) -> str:
    env = {**os.environ, **extra_env}
    result = subprocess.run(
        [sys.executable, "-c", _CODE], capture_output=True, text=True, env=env, check=True
    )
    return result.stdout.strip()


def test_import_sets_ort_disable_telemetry() -> None:
    env = {k: v for k, v in os.environ.items() if k != "ORT_DISABLE_TELEMETRY"}
    result = subprocess.run(
        [sys.executable, "-c", _CODE], capture_output=True, text=True, env=env, check=True
    )
    assert result.stdout.strip() == "1"


def test_import_overrides_a_preset_value() -> None:
    assert _run({"ORT_DISABLE_TELEMETRY": "0"}) == "1"


def test_onnxruntime_not_imported_by_the_package_init() -> None:
    code = "import sys, lector_placas; print('onnxruntime' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
