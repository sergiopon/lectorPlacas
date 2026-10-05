from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "nivel_f.py"

pytestmark = pytest.mark.integration


def test_web_loopback_check_passes() -> None:
    if shutil.which("ss") is None:
        pytest.skip("ss no disponible")
    spec = importlib.util.spec_from_file_location("nivel_f", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok, detail = module.check_web_loopback()
    assert ok
    assert detail.startswith("bind=ok host=ok auth=ok")
