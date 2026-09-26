from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def constant_output_model(path: Path, output: np.ndarray, input_size: int = 64) -> Path:
    """Modelo ONNX sintético: ignora la entrada `images` y devuelve `output0` constante."""
    value = numpy_helper.from_array(output.astype(np.float32), name="const_value")
    node = helper.make_node("Constant", inputs=[], outputs=["output0"], value=value)
    graph = helper.make_graph(
        [node],
        "synthetic",
        [
            helper.make_tensor_value_info(
                "images", TensorProto.FLOAT, [1, 3, input_size, input_size]
            )
        ],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(output.shape))],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path
