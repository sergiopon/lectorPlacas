from __future__ import annotations

import re

import pytest

from lector_placas.cli.evaluation_commands import _write_video_summary
from lector_placas.evaluation.metrics import PlateMetrics


def test_summary_line(capsys: pytest.CaptureFixture[str]) -> None:
    metrics = PlateMetrics(
        2,
        2,
        2,
        2,
        0,
        gt_far_excluded=1,
        confirmed_matched_near=1,
        min_plate_width=48,
    )
    _write_video_summary(metrics, speed_factor=1.5, peak_mib=None, report_name="r.json")
    first_line = capsys.readouterr().out.splitlines()[0]
    assert "gt_far_excluded=1 min_plate_width=48 speed_factor=" in first_line
    assert re.search(r"[A-Z]{3}\d{3}", first_line) is None
