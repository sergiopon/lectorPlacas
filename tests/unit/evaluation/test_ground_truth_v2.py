from __future__ import annotations

import json
from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.ground_truth import load_ground_truth

V1_DOCS = {
    "version": 1,
    "video_sha256": "a" * 64,
    "subset": "street_day",
    "camera": "fixed",
    "plates": [
        {
            "text": "ABC123",
            "vehicle_type": "car",
            "first_seen_ms": 1200,
            "last_seen_ms": 4300,
            "legible": True,
        },
        {
            "text": "XYZ98K",
            "vehicle_type": "motorcycle",
            "first_seen_ms": 5000,
            "last_seen_ms": 6100,
            "legible": True,
        },
        {
            "text": "",
            "vehicle_type": "truck",
            "first_seen_ms": 7000,
            "last_seen_ms": 7900,
            "legible": False,
        },
    ],
}

V2_VALID = {
    "version": 2,
    "video_sha256": "a" * 64,
    "subset": "patrol",
    "camera": "vehicle_mounted",
    "plates": [
        {
            "text": "ABC123",
            "vehicle_type": "car",
            "first_seen_ms": 1200,
            "last_seen_ms": 4300,
            "legible": True,
            "max_plate_width_px": 60,
        },
        {
            "text": "",
            "vehicle_type": "truck",
            "first_seen_ms": 7000,
            "last_seen_ms": 7900,
            "legible": False,
        },
    ],
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "gt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_v1_still_loads(tmp_path: Path) -> None:
    truth = load_ground_truth(write(tmp_path, V1_DOCS))
    assert truth.version == 1
    assert all(plate.max_plate_width_px is None for plate in truth.plates)


def test_v2_requires_width_on_legible(tmp_path: Path) -> None:
    missing = json.loads(json.dumps(V2_VALID))
    del missing["plates"][0]["max_plate_width_px"]
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, missing))
    truth = load_ground_truth(write(tmp_path, V2_VALID))
    assert truth.plates[0].max_plate_width_px == 60
    assert truth.plates[1].max_plate_width_px is None


def test_v1_rejects_v2_fields(tmp_path: Path) -> None:
    with_width = json.loads(json.dumps(V1_DOCS))
    with_width["plates"][0]["max_plate_width_px"] = 60
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, with_width))

    mounted = json.loads(json.dumps(V1_DOCS))
    mounted["camera"] = "vehicle_mounted"
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, mounted))

    patrol = json.loads(json.dumps(V1_DOCS))
    patrol["subset"] = "patrol"
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, patrol))

    truth = load_ground_truth(write(tmp_path, V2_VALID))
    assert truth.subset == "patrol" and truth.camera == "vehicle_mounted"


def test_width_must_be_positive(tmp_path: Path) -> None:
    data = json.loads(json.dumps(V2_VALID))
    data["plates"][0]["max_plate_width_px"] = 0
    with pytest.raises(EvaluationError):
        load_ground_truth(write(tmp_path, data))
