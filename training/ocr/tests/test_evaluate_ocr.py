from __future__ import annotations

import csv
import dataclasses
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import pytest

from ocr_training import evaluate_ocr as ev
from ocr_training.common import TrainingError, sha256_file


def make_split(root: Path, texts: Sequence[str], split: str = "test", prefix: str = "real",
               with_groups: bool = True) -> Path:
    split_dir = root / split
    (split_dir / "images").mkdir(parents=True)
    rows, groups = [], []
    for i, text in enumerate(texts):
        name = f"{prefix}_{i:06d}.png"
        assert cv2.imwrite(str(split_dir / "images" / name), np.full((16, 32, 3), i, np.uint8))
        rows.append((f"images/{name}", text))
        groups.append((f"images/{name}", f"g{i // 2:05d}"))
    for file_name, header, body in (("annotations.csv", ("image_path", "plate_text"), rows),
                                    ("groups.csv", ("image_path", "group_id"), groups)):
        if file_name == "groups.csv" and not with_groups:
            continue
        with (split_dir / file_name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(body)
    return split_dir / "annotations.csv"


def fake_factory(truths: Sequence[str]) -> ev.PredictorFactory:
    def factory(model: Path, config: Path) -> ev.Predictor:
        def predict(images: Sequence[npt.NDArray[np.uint8]]) -> list[str]:
            texts = [truths[int(image[0, 0, 0])] for image in images]
            return texts if model.name == "candidate.onnx" else [t[:-1] for t in texts]
        return predict
    return factory


def metrics(**changes: object) -> ev.ModelMetrics:
    base = ev.ModelMetrics(150, 0.02, 0.9, (0.01, 0.04), {"moto": 0.02, "motocarro": None, "other": 0.02},
                           {"moto": 30, "motocarro": 0, "other": 120})
    return dataclasses.replace(base, **changes)


def test_levenshtein_and_normalize() -> None:
    assert ev.levenshtein("", "ABC") == 3
    assert ev.levenshtein("ABC", "ABD") == 1
    assert ev.levenshtein("ABC123", "ABC12") == 1
    assert ev.normalize_prediction("AB_12") == ""
    assert ev.normalize_prediction("abc123") == ""
    assert ev.normalize_prediction("ABC123") == "ABC123"


def test_compute_metrics() -> None:
    result = ev.compute_metrics(["ABC123", "XYZ98"], ["ABC123", "XYZ98K"], ["g1", "g2"], 0)
    assert result.samples == 2
    assert result.cer == pytest.approx(1 / 12)
    assert result.exact_match_rate == 0.5
    low, high = result.cer_ci95
    assert 0.0 <= low <= result.cer <= high <= 1 / 6 + 1e-12
    assert result.cer_by_category == {"moto": pytest.approx(1 / 6), "motocarro": None, "other": 0.0}
    assert result.samples_by_category == {"moto": 1, "motocarro": 0, "other": 1}
    assert ev.compute_metrics(["ABC123", "XYZ98"], ["ABC123", "XYZ98K"], ["g1", "g2"], 0) == result
    with pytest.raises(TrainingError):
        ev.compute_metrics([], [], [], 0)


def test_decide() -> None:
    baseline = metrics(cer=0.10, exact_match_rate=0.6)
    assert ev.decide(metrics(), baseline) == []
    assert len(ev.decide(metrics(samples=90), baseline)) == 1
    assert len(ev.decide(metrics(cer=0.04), baseline)) == 1
    assert len(ev.decide(metrics(cer_ci95=(0.01, 0.06)), baseline)) == 1
    assert len(ev.decide(metrics(), metrics(cer=0.01, exact_match_rate=0.6))) == 1
    assert len(ev.decide(metrics(), metrics(cer=0.10, exact_match_rate=0.95))) == 1


def test_evaluate_accepts_better_candidate(tmp_path: Path) -> None:
    truths = [f"ABC{i:03d}" for i in range(120)]
    crops = make_split(tmp_path, truths)
    report = ev.evaluate(crops, tmp_path / "candidate.onnx", tmp_path / "base.onnx", tmp_path / "cfg.yaml", 0,
                         fake_factory(truths))
    assert report["accepted"] is True and report["reasons"] == []
    assert report["samples"] == 120
    assert report["candidate"]["cer"] == 0.0
    assert report["baseline"]["cer"] == pytest.approx(1 / 6)
    assert "ABC0" not in json.dumps(report)


def test_evaluate_rejects_small_sample(tmp_path: Path) -> None:
    truths = [f"ABC{i:03d}" for i in range(50)]
    crops = make_split(tmp_path, truths)
    report = ev.evaluate(crops, tmp_path / "candidate.onnx", tmp_path / "base.onnx", tmp_path / "cfg.yaml", 0,
                         fake_factory(truths))
    assert report["accepted"] is False and len(report["reasons"]) == 1


@pytest.mark.parametrize("kwargs", [{"split": "val"}, {"prefix": "syn"}, {"with_groups": False}])
def test_read_split_errors(tmp_path: Path, kwargs: dict[str, object]) -> None:
    crops = make_split(tmp_path, ["ABC123", "ABC124"], **kwargs)  # type: ignore[arg-type]
    with pytest.raises(TrainingError):
        ev.read_split(crops)


def test_read_split_accepts_test_video(tmp_path: Path) -> None:
    crops = make_split(tmp_path, ["ABC123", "ABC124"], split="test_video")
    rows = ev.read_split(crops)
    assert [(text, group) for _, text, group in rows] == [("ABC123", "g00000"), ("ABC124", "g00000")]
    with pytest.raises(TrainingError):
        ev.read_split(make_split(tmp_path / "otro", ["ABC123"], split="val"))


def test_custom_baseline_is_used_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    truths = [f"ABC{i:03d}" for i in range(120)]
    make_split(tmp_path, truths, split="test_video")
    baseline = tmp_path / "runs" / "colombia_v1" / "best.onnx"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"onnx de prueba")
    (tmp_path / "candidate.onnx").write_bytes(b"onnx de prueba")
    monkeypatch.setattr(ev, "DATASETS_DIR", tmp_path)
    monkeypatch.setattr(ev, "TRAINING_DIR", tmp_path)
    monkeypatch.setattr(ev, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(ev, "require_asset", lambda name: tmp_path / "cfg.yaml")
    monkeypatch.setattr(ev, "check_ocr_onnx", lambda path: None)
    monkeypatch.setattr(ev, "onnx_predictor", fake_factory(truths))
    assert ev.main(["--crops", "test_video/annotations.csv", "--candidate", "candidate.onnx",
                    "--baseline", "runs/colombia_v1/best.onnx"]) == 0
    report = json.loads(next((tmp_path / "reports").iterdir()).read_text(encoding="utf-8"))
    assert report["baseline_model_id"] == "custom"
    assert report["split"] == "test_video"
    assert report["baseline_path"] == "runs/colombia_v1/best.onnx"
    assert report["baseline_sha256"] == sha256_file(baseline)
    assert report["baseline"]["cer"] == pytest.approx(1 / 6)


def test_write_report(tmp_path: Path) -> None:
    now = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    path = ev.write_report({"accepted": True}, tmp_path / "reports", now)
    assert path.name == "ocr-eval-20260927T100000Z.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"accepted": True}
    with pytest.raises(TrainingError):
        ev.write_report({"accepted": True}, tmp_path / "reports", now)
    with pytest.raises(TrainingError):
        ev.write_report({}, tmp_path / "reports", datetime(2026, 9, 27, 11, 0, 0))
