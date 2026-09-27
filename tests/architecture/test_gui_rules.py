from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "lector_placas"
FORBIDDEN_TOKENS = ("QSettings", "QtNetwork", "QClipboard", "clipboard(", "imshow", "namedWindow")
WINDOW_TITLE_CALL = re.compile(r"setWindowTitle\((?![A-Z][A-Z0-9_]*\))")


@pytest.mark.parametrize("path", sorted((SRC / "gui").glob("*.py")), ids=lambda path: path.name)
def test_gui_source_has_no_forbidden_patterns(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in text, f"{path.name}: contiene {token!r}"
    assert WINDOW_TITLE_CALL.search(text) is None, f"{path.name}: setWindowTitle con texto literal"
