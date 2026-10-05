"""Tests de aceptación adicionales.

Viven en `training/ocr/tests/` y no en `tests/review/` porque `training/ocr` es un
proyecto uv independiente que el pytest de la raíz no recoge.

Cubren lo que el test de aceptación solo mira por índices: la lista de argumentos
completa de `train`, la estrictura de `validate_annotations`, los rechazos de
`check_ocr_onnx` y las guardias de rutas del dataset sintético de smoke test.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import cv2
import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from ocr_training.common import (
    WEIGHTS_DIR,
    TrainingError,
    check_ocr_onnx,
    find_best_model,
    require_asset,
    validate_annotations,
)
from ocr_training.make_smoke_dataset import make_smoke_dataset
from ocr_training.train import build_parser, train_arguments


def ocr_model(
    path: Path,
    input_name: str = "input",
    dtype: int = TensorProto.UINT8,
    shape: tuple[object, ...] = ("batch", 64, 128, 3),
    output_name: str = "plate",
) -> Path:
    value = numpy_helper.from_array(np.zeros((1, 370), dtype=np.float32), name="v")
    node = helper.make_node("Constant", [], [output_name], value=value)
    graph = helper.make_graph(
        [node],
        "g",
        [helper.make_tensor_value_info(input_name, dtype, list(shape))],
        [helper.make_tensor_value_info(output_name, TensorProto.FLOAT, [1, 370])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def write_csv(root: Path, body: str) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "images" / "a.png").write_bytes(b"png")
    path = root / "annotations.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_train_arguments_is_the_exact_expected_list(tmp_path: Path) -> None:
    """La lista de argumentos de la CLI no puede ganar, perder ni reordenar elementos."""
    args = build_parser().parse_args(
        ["--train", "a.csv", "--val", "b.csv", "--name", "run1", "--epochs", "7", "--batch-size", "8"]
    )
    result = train_arguments(args, tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "run1")
    assert result == [
        "train",
        "--model-config-file",
        str(WEIGHTS_DIR / "cct_xs_v2_global_model_config.yaml"),
        "--plate-config-file",
        str(WEIGHTS_DIR / "cct_xs_v2_global_plate_config.yaml"),
        "--annotations",
        str(tmp_path / "a.csv"),
        "--val-annotations",
        str(tmp_path / "b.csv"),
        "--weights-path",
        str(WEIGHTS_DIR / "cct_xs_v2_global.keras"),
        "--epochs",
        "7",
        "--batch-size",
        "8",
        "--early-stopping-patience",
        "100",
        "--seed",
        "0",
        "--validate-dataset",
        "error",
        "--output-dir",
        str(tmp_path / "run1"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        "image_path,plate_text,extra\nimages/a.png,ABC123,x\n",
        "image_path,plate_text\nimages/a.png,ABCDEFGHIJK\n",
        "image_path,plate_text\n.,ABC123\n",
        "image_path,plate_text\nimages/a.png,\n",
    ],
)
def test_validate_annotations_rejects_malformed_rows(tmp_path: Path, body: str) -> None:
    """Columnas exactas, texto de hasta 10 caracteres y una imagen real por fila."""
    with pytest.raises(TrainingError):
        validate_annotations(write_csv(tmp_path / "bad", body))


def test_validate_annotations_reports_the_plate_region_column(tmp_path: Path) -> None:
    """La columna `plate_region` tiene un mensaje propio porque desactiva la cabeza de región."""
    csv_path = write_csv(
        tmp_path / "region", "image_path,plate_text,plate_region\nimages/a.png,ABC123,Colombia\n"
    )
    with pytest.raises(TrainingError, match="plate_region"):
        validate_annotations(csv_path)


@pytest.mark.parametrize(
    "index,kwargs",
    [
        (0, {"input_name": "images"}),
        (1, {"dtype": TensorProto.FLOAT}),
        (2, {"shape": ("batch", 128, 64, 3)}),
        (3, {"shape": ("batch", 64, 128, 1)}),
        (4, {"output_name": "logits"}),
    ],
)
def test_check_ocr_onnx_rejects_contract_violations(
    tmp_path: Path, index: int, kwargs: dict
) -> None:
    """Entrada `input` uint8 `[*, 64, 128, 3]` y alguna salida `plate`, o error."""
    path = ocr_model(tmp_path / f"bad{index}.onnx", **kwargs)
    with pytest.raises(TrainingError):
        check_ocr_onnx(path)


def test_find_best_model_needs_exactly_one_run(tmp_path: Path) -> None:
    """Dos subdirectorios de corrida son ambiguos; también falta `best.keras`."""
    for name in ("run_a", "run_b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "best.keras").write_bytes(b"k")
    with pytest.raises(TrainingError):
        find_best_model(tmp_path)
    only = tmp_path / "only"
    only.mkdir()
    with pytest.raises(TrainingError):
        find_best_model(only)


def test_require_asset_rejects_unknown_names() -> None:
    """Solo los tres recursos declarados en `ASSETS` son aceptables."""
    with pytest.raises(TrainingError):
        require_asset("cct_xs_v2_global.onnx")


def test_smoke_dataset_stays_inside_datasets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El smoke test no puede escribir fuera de `DATASETS_DIR` ni sobrescribir una salida."""
    import ocr_training.make_smoke_dataset as smoke

    monkeypatch.setattr(smoke, "DATASETS_DIR", tmp_path)
    with pytest.raises(TrainingError):
        make_smoke_dataset(tmp_path.parent / "fuera", 2, 1, 0)
    make_smoke_dataset(tmp_path / "smoke", 2, 1, 0)
    with pytest.raises(TrainingError):
        make_smoke_dataset(tmp_path / "smoke", 2, 1, 0)


def test_smoke_dataset_texts_and_image_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Los textos sintéticos siguen los patrones de placa y las imágenes son 64x128 RGB."""
    import ocr_training.make_smoke_dataset as smoke

    monkeypatch.setattr(smoke, "DATASETS_DIR", tmp_path)
    make_smoke_dataset(tmp_path / "smoke", 4, 2, 3)
    rows = list(csv.DictReader((tmp_path / "smoke" / "train" / "annotations.csv").open(encoding="utf-8")))
    assert len(rows) == 4
    patterns = (r"^[A-Z]{3}[0-9]{3}$", r"^[A-Z]{3}[0-9]{2}[A-Z]$")
    assert all(any(re.fullmatch(p, row["plate_text"]) for p in patterns) for row in rows)
    image = cv2.imread(str(tmp_path / "smoke" / "train" / rows[0]["image_path"]))
    assert image.shape == (64, 128, 3)
