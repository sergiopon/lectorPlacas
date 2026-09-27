from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.domain.entities import BoundingBox, PlateDetection
from lector_placas.infrastructure import network_guard

ROOT = Path(__file__).resolve().parents[3]


class FakeDetector:
    def detect(self, image):  # type: ignore[no-untyped-def]
        return [PlateDetection(BoundingBox(50, 40, 150, 60), 0.9)]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.setattr(composition, "build_registry", lambda config: None)
    monkeypatch.setattr(
        composition, "build_plate_detector", lambda config, registry: FakeDetector()
    )
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    merged = tmp_path / "training" / "detector" / "datasets" / "merged"
    (merged / "images" / "val").mkdir(parents=True)
    (merged / "labels" / "val").mkdir(parents=True)
    for name in ("x1", "x2"):
        cv2.imwrite(
            str(merged / "images" / "val" / f"{name}.png"), np.zeros((100, 200, 3), np.uint8)
        )
    (merged / "labels" / "val" / "x1.txt").write_text("0 0.5 0.5 0.5 0.2\n", encoding="utf-8")
    cv2.imwrite(str(merged / "images" / "val" / "tiny.png"), np.zeros((8, 8, 3), np.uint8))
    return tmp_path


def test_parser_defaults() -> None:
    args = cli_main.build_parser().parse_args(["evaluate-detector"])
    assert (args.split, args.iou, args.network) == ("val", 0.5, False)
    assert getattr(args, "key", None) is None


def test_evaluate_detector_writes_report(project: Path) -> None:
    code = cli_main.main(["--config", str(project / "config" / "lector.yaml"), "evaluate-detector"])
    assert code == 0
    report = next((project / "data" / "eval" / "reports").glob("report-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert (data["kind"], data["images"], data["skipped"]) == ("detector", 2, 1)
    assert (data["true_positives"], data["false_positives"], data["false_negatives"]) == (1, 1, 0)
    assert data["precision"] == pytest.approx(0.5)
    assert data["recall"] == pytest.approx(1.0)
    assert "x1" not in report.read_text(encoding="utf-8")


def test_invalid_iou_exits_nonzero(project: Path) -> None:
    code = cli_main.main(
        ["--config", str(project / "config" / "lector.yaml"), "evaluate-detector", "--iou", "1.5"]
    )
    assert code != 0
