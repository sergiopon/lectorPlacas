from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.domain.entities import OcrResult
from lector_placas.infrastructure import network_guard

ROOT = Path(__file__).resolve().parents[3]


class FakeReader:
    def read(self, plate_images):  # type: ignore[no-untyped-def]
        return [OcrResult("ABC123", (0.9,) * 6) for _ in plate_images]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.setattr(composition, "build_registry", lambda config: None)
    monkeypatch.setattr(composition, "build_reader", lambda config, registry: FakeReader())
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


def test_parser_registers_evaluation_commands() -> None:
    parser = cli_main.build_parser()
    args = parser.parse_args(
        ["evaluate", "--video", "v.mp4", "--ground-truth", "g.json", "--skip-vram"]
    )
    assert (args.video, args.ground_truth, args.skip_vram, args.network) == (
        Path("v.mp4"),
        Path("g.json"),
        True,
        False,
    )
    assert parser.parse_args(["evaluate-ocr", "--crops", "c.csv"]).crops == Path("c.csv")


def test_evaluate_ocr_writes_report_without_plates(project: Path) -> None:
    crops = project / "data" / "eval" / "ocr_crops"
    (crops / "images").mkdir(parents=True)
    for name in ("a.png", "b.png"):
        cv2.imwrite(str(crops / "images" / name), np.zeros((20, 60, 3), np.uint8))
    (crops / "annotations.csv").write_text(
        "image_path,plate_text\nimages/a.png,ABC123\nimages/b.png,ABC128\n", encoding="utf-8"
    )
    code = cli_main.main(
        [
            "--config",
            str(project / "config" / "lector.yaml"),
            "evaluate-ocr",
            "--crops",
            str(crops / "annotations.csv"),
        ]
    )
    assert code == 0
    report = next((project / "data" / "eval" / "reports").glob("report-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["samples"] == 2
    assert data["cer"] == pytest.approx(1 / 12)
    assert data["exact_match_rate"] == pytest.approx(0.5)
    assert "ABC" not in report.read_text(encoding="utf-8")
