from __future__ import annotations

from pathlib import Path

from lector_placas.cli.main import build_parser
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]


def test_parser_registers_export_reviewed() -> None:
    args = build_parser().parse_args(["dataset", "export-reviewed"])
    assert (args.key, args.network) == ("load", False)


def test_config_has_training_retention() -> None:
    assert load_config(ROOT / "config" / "lector.yaml").retention.training_days == 180
