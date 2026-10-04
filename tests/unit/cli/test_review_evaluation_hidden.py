"""Tests del resumen oculto en review_evaluation_commands (spec 064)."""

from __future__ import annotations

import sys
from io import StringIO

from lector_placas.cli.review_evaluation_commands import _write_summary
from lector_placas.evaluation.review_metrics import ReviewMetrics


def test_summary_includes_hidden_line() -> None:
    """_write_summary incluye la línea oculta entre métricas y reporte."""
    metrics = ReviewMetrics(
        confirmed_total=10,
        confirmed_audited=8,
        confirmed_kept=6,
        confirmed_corrected=1,
        confirmed_rejected=1,
        precision_confirmed=0.75,
        unverified_total=5,
        unverified_confirmed=0,
        unverified_corrected=1,
        unverified_rejected=0,
        unverified_pending=4,
        reason_counts={"low_confidence": 2},
        reviewed_readings=2,
        cer=None,
        exact_match_rate=None,
        confirmed_illegible=0,
        unverified_illegible=0,
        hidden_total=3,
        hidden_legible=1,
        hidden_unusable=1,
        hidden_pending=1,
    )
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        _write_summary(metrics, "r.json")
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
    lines = output.strip().split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("confirmed_audited=8")
    assert lines[1] == "ocultas=3 ocultas_legibles=1 ocultas_inservibles=1 ocultas_pendientes=1"
    assert lines[2] == "reporte=r.json"
