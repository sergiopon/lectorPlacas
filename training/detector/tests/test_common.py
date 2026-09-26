from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import onnx
import pytest
import yaml
from onnx import TensorProto, helper, numpy_helper

from detector_training.common import (
    TrainingError, check_end2end_onnx, require_sha256, set_offline_env, sha256_file,
    validate_single_class_dataset,
)


def constant_model(path: Path, shape: tuple[int, ...], size: int = 64) -> Path:
    value = numpy_helper.from_array(np.zeros(shape, dtype=np.float32), name="v")
    node = helper.make_node("Constant", [], ["output0"], value=value)
    graph = helper.make_graph(
        [node], "g", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, size, size])],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(shape))])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def test_sha_helpers(tmp_path: Path) -> None:
    path = tmp_path / "w.pt"
    path.write_bytes(b"pesos")
    digest = hashlib.sha256(b"pesos").hexdigest()
    assert sha256_file(path) == digest
    require_sha256(path, digest)
    with pytest.raises(TrainingError):
        require_sha256(path, "0" * 64)
    with pytest.raises(TrainingError):
        require_sha256(tmp_path / "no.pt", digest)


def test_offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOLO_OFFLINE", raising=False)
    monkeypatch.delenv("YOLO_AUTOINSTALL", raising=False)
    set_offline_env()
    assert (os.environ["YOLO_OFFLINE"], os.environ["YOLO_AUTOINSTALL"]) == ("True", "False")


def test_check_end2end_onnx(tmp_path: Path) -> None:
    check_end2end_onnx(constant_model(tmp_path / "ok.onnx", (1, 300, 6)), 64)
    with pytest.raises(TrainingError):
        check_end2end_onnx(constant_model(tmp_path / "bad.onnx", (1, 84, 8400)), 64)
    with pytest.raises(TrainingError):
        check_end2end_onnx(constant_model(tmp_path / "size.onnx", (1, 300, 6), size=32), 64)


@pytest.mark.parametrize("names,ok", [
    ({0: "plate"}, True), (["plate"], True), (["placa"], False), (["plate", "car"], False),
])
def test_validate_single_class_dataset(tmp_path: Path, names: object, ok: bool) -> None:
    data = tmp_path / "data.yaml"
    data.write_text(yaml.safe_dump({"path": ".", "train": "images/train", "val": "images/val", "names": names}))
    if ok:
        validate_single_class_dataset(data)
    else:
        with pytest.raises(TrainingError):
            validate_single_class_dataset(data)
