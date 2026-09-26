from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.gpu
def test_verify_gpu_script_reports_blackwell_and_cuda_provider() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_gpu.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "compute_cap=12.0" in result.stdout
