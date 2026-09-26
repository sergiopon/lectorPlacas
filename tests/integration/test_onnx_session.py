from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.inference.onnx_session import create_session, providers_for
from lector_placas.domain.errors import ModelLoadError
from tests.fixtures.synthetic_onnx import constant_output_model

pytestmark = pytest.mark.integration


def test_providers_for() -> None:
    assert providers_for("cpu") == ["CPUExecutionProvider"]
    assert providers_for("cuda") == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_cpu_session_runs_synthetic_model(tmp_path: Path) -> None:
    expected = np.arange(12, dtype=np.float32).reshape(1, 2, 6)
    session = create_session(constant_output_model(tmp_path / "m.onnx", expected), "cpu")
    outputs = session.run(None, {"images": np.zeros((1, 3, 64, 64), dtype=np.float32)})
    np.testing.assert_array_equal(outputs[0], expected)


def test_invalid_model_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"no es onnx")
    with pytest.raises(ModelLoadError):
        create_session(bad, "cpu")


@pytest.mark.gpu
def test_cuda_session(tmp_path: Path) -> None:
    expected = np.ones((1, 1, 6), dtype=np.float32)
    session = create_session(constant_output_model(tmp_path / "m.onnx", expected), "cuda")
    outputs = session.run(None, {"images": np.zeros((1, 3, 64, 64), dtype=np.float32)})
    np.testing.assert_array_equal(outputs[0], expected)
