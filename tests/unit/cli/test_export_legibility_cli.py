from __future__ import annotations

from pathlib import Path

from lector_placas.cli.composition import LEGIBILITY_EXPORT_DIR, build_legibility_store
from lector_placas.cli.main import build_parser
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]


def test_parser_registers_export_legibility() -> None:
    args = build_parser().parse_args(["dataset", "export-legibility"])
    assert (args.key, args.network) == ("load", False)


def test_legibility_store_under_training() -> None:
    config = load_config(ROOT / "config" / "lector.yaml")
    store = build_legibility_store(config)
    assert store._root == config.root_dir / LEGIBILITY_EXPORT_DIR
