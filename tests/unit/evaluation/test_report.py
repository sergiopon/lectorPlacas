from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.report import write_report

T0 = datetime(2026, 9, 24, 12, 0, 1, tzinfo=UTC)


def test_writes_private_json(tmp_path: Path) -> None:
    path = write_report(tmp_path / "reports", {"kind": "ocr", "cer": 0.02}, T0)
    assert path.name == "report-20260924T120001Z.json"
    assert json.loads(path.read_text(encoding="utf-8"))["cer"] == 0.02
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(EvaluationError):
        write_report(tmp_path / "reports", {"kind": "ocr"}, T0)


def test_rejects_plate_text(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError):
        write_report(tmp_path / "reports", {"nota": "ABC123"}, T0)
