from __future__ import annotations

from lector_placas.cli.main import build_parser
from lector_placas.cli.review_evaluation_commands import cmd_evaluate_review


def test_parser_review_status_and_evaluate_review() -> None:
    parser = build_parser()
    assert parser.parse_args(["review"]).status == "unverified"
    assert parser.parse_args(["review", "--status", "confirmed"]).status == "confirmed"
    args = parser.parse_args(["evaluate-review"])
    assert (args.handler, args.network, args.key) == (cmd_evaluate_review, False, "load")
