from __future__ import annotations

import json
from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.ground_truth import load_ground_truth

VALID = {
    "version": 1,
    "video_sha256": "a" * 64,
    "subset": "street_day",
    "camera": "fixed",
    "plates": [
        {
            "text": "ABC123",
            "vehicle_type": "car",
            "first_seen_ms": 1,
            "last_seen_ms": 2,
            "legible": True,
        },
        {
            "text": "",
            "vehicle_type": "truck",
            "first_seen_ms": 3,
            "last_seen_ms": 4,
            "legible": False,
        },
    ],
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "gt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_ground_truth(tmp_path: Path) -> None:
    truth = load_ground_truth(write(tmp_path, VALID))
    assert truth.camera == "fixed" and len(truth.plates) == 2


@pytest.mark.parametrize(
    "plate_patch",
    [
        {"text": "abc123"},
        {"text": "", "legible": True},
        {"text": "ABC123", "legible": False},
        {"first_seen_ms": 5, "last_seen_ms": 2},
        {"first_seen_ms": -1},
    ],
)
def test_invalid_plates(tmp_path: Path, plate_patch: dict[str, object]) -> None:
    data = json.loads(json.dumps(VALID))
    data["plates"][0].update(plate_patch)
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, data))


def test_invalid_file(tmp_path: Path) -> None:
    bad = tmp_path / "gt.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(EvaluationError):
        load_ground_truth(bad)
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, {**VALID, "subset": "otro"}))
