from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError, UnsafePathError
from lector_placas.evaluation.ocr_dataset import read_ocr_annotations


def write_csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "annotations.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_reads_rows(tmp_path: Path) -> None:
    rows = read_ocr_annotations(write_csv(tmp_path, "image_path,plate_text\nimages/a.png,ABC123\n"))
    assert rows == [((tmp_path / "images" / "a.png").resolve(), "ABC123")]


@pytest.mark.parametrize(
    "body,error",
    [
        ("image,plate_text\na.png,ABC123\n", EvaluationError),
        ("image_path,plate_text\na.png,abc\n", EvaluationError),
        ("image_path,plate_text\n", EvaluationError),
        ("image_path,plate_text\n../x.png,ABC123\n", UnsafePathError),
    ],
)
def test_invalid(tmp_path: Path, body: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        read_ocr_annotations(write_csv(tmp_path, body))
