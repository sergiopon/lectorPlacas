from __future__ import annotations

from pathlib import Path

from lector_placas.cli.main import build_parser


def test_dataset_subcommands() -> None:
    parser = build_parser()
    merge = parser.parse_args(
        ["dataset", "merge-detection", "--sources", "s.yaml", "--output", "merged"]
    )
    assert (merge.sources, merge.output, merge.network) == (Path("s.yaml"), "merged", False)
    chars = parser.parse_args(["dataset", "chars-to-ocr", "--source", "raw/x", "--output", "ocr1"])
    assert (chars.source, chars.output) == (Path("raw/x"), "ocr1")
