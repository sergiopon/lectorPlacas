"""Tests de aceptación adicionales.

Cubren casos borde que la spec no enumera explícitamente: scores no finitos (NaN) y
cajas completamente fuera del lienzo letterbox, que deben descartarse sin romper el
decodificador.
"""

from __future__ import annotations

import numpy as np

from lector_placas.adapters.inference.letterbox import LetterboxTransform, letterbox
from lector_placas.adapters.inference.yolo_end2end import decode_end2end


def transform() -> LetterboxTransform:
    return letterbox(np.zeros((100, 200, 3), dtype=np.uint8), 64)[1]


def test_nan_score_is_skipped() -> None:
    """Una fila con score NaN se descarta por no ser finito."""
    output = np.array(
        [
            [
                [0, 16, 64, 48, np.nan, 2],
                [0, 16, 64, 48, 0.8, 7],
            ]
        ],
        dtype=np.float32,
    )
    result = decode_end2end(output, transform(), 0.25)
    assert [d.class_id for d in result] == [7]


def test_box_outside_canvas_is_skipped() -> None:
    """Una caja totalmente fuera del lienzo (negativa o más allá del borde) se descarta."""
    output = np.array(
        [
            [
                [-50, -50, -10, -10, 0.9, 3],
                [1000, 1000, 2000, 2000, 0.9, 4],
                [0, 16, 64, 48, 0.8, 7],
            ]
        ],
        dtype=np.float32,
    )
    result = decode_end2end(output, transform(), 0.25)
    assert [d.class_id for d in result] == [7]
