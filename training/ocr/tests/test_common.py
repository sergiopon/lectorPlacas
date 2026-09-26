from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from ocr_training.common import (
    TrainingError,
    check_ocr_onnx,
    find_best_model,
    sha256_file,
    validate_annotations,
)
from ocr_training.train import build_parser, train_arguments


def ocr_model(
    path: Path,
    input_name: str = "input",
    dtype: int = TensorProto.UINT8,
    output_name: str = "plate",
) -> Path:
    value = numpy_helper.from_array(np.zeros((1, 370), dtype=np.float32), name="v")
    node = helper.make_node("Constant", [], [output_name], value=value)
    graph = helper.make_graph(
        [node],
        "g",
        [helper.make_tensor_value_info(input_name, dtype, ["batch", 64, 128, 3])],
        [helper.make_tensor_value_info(output_name, TensorProto.FLOAT, [1, 370])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def write_csv(root: Path, body: str, images: tuple[str, ...] = ("a.png",)) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    for name in images:
        (root / "images" / name).write_bytes(b"png")
    path = root / "annotations.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_sha256(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_validate_annotations(tmp_path: Path) -> None:
    assert (
        validate_annotations(
            write_csv(tmp_path / "ok", "image_path,plate_text\nimages/a.png,ABC123\n")
        )
        == 1
    )


@pytest.mark.parametrize(
    "body",
    [
        "image_path,plate_text,plate_region\nimages/a.png,ABC123,Colombia\n",
        "image_path,plate_text\nimages/a.png,abc123\n",
        "image_path,plate_text\nimages/missing.png,ABC123\n",
        "image_path,plate_text\n../a.png,ABC123\n",
        "image_path,plate_text\n",
    ],
)
def test_validate_annotations_errors(tmp_path: Path, body: str) -> None:
    with pytest.raises(TrainingError):
        validate_annotations(write_csv(tmp_path / "bad", body))


def test_find_best_model(tmp_path: Path) -> None:
    with pytest.raises(TrainingError):
        find_best_model(tmp_path)
    run = tmp_path / "2026-09-26_10-00-00"
    run.mkdir()
    (run / "best.keras").write_bytes(b"k")
    assert find_best_model(tmp_path) == run / "best.keras"


def test_check_ocr_onnx(tmp_path: Path) -> None:
    check_ocr_onnx(ocr_model(tmp_path / "ok.onnx"))
    with pytest.raises(TrainingError):
        check_ocr_onnx(ocr_model(tmp_path / "f.onnx", dtype=TensorProto.FLOAT))
    with pytest.raises(TrainingError):
        check_ocr_onnx(ocr_model(tmp_path / "o.onnx", output_name="logits"))


def test_train_arguments(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--train", "a.csv", "--val", "b.csv", "--name", "run1"])
    result = train_arguments(args, tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "run1")
    assert result[0] == "train"
    assert result[result.index("--epochs") + 1] == "150"
    assert result[result.index("--validate-dataset") + 1] == "error"
    assert result[result.index("--output-dir") + 1] == str(tmp_path / "run1")
    assert result[result.index("--weights-path") + 1].endswith("cct_xs_v2_global.keras")
