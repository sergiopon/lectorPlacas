from __future__ import annotations

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
_EXCLUDED = {"node_modules", "dist"}
_URL = re.compile(r"https?://")


def _files(base: Path) -> list[Path]:
    return [
        path
        for path in sorted(base.rglob("*"))
        if path.is_file() and not _EXCLUDED.intersection(path.relative_to(FRONTEND).parts)
    ]


def _source_files() -> list[Path]:
    return [*_files(FRONTEND / "src"), FRONTEND / "index.html"]


def test_no_figma_artifacts() -> None:
    assert not (FRONTEND / ".figma").exists()
    assert not (FRONTEND / "AGENTS.md").exists()
    assert not (FRONTEND / "pnpm-lock.yaml").exists()
    assert not (FRONTEND / "src" / "api" / "mock.ts").exists()
    config = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    for forbidden in ("figma", "googletagmanager", "gtag", ".".join(["0"] * 4)):
        assert forbidden not in config


def test_no_remote_resources() -> None:
    for path in _source_files():
        text = path.read_text(encoding="utf-8").replace("http://www.w3.org/", "")
        assert _URL.search(text) is None, str(path)


def test_exact_versions() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name, version in package[section].items():
            assert not version.startswith(("^", "~")), name
    assert package["engines"]["node"] == ">=22.12.0"


def test_api_is_single_entry() -> None:
    api_dir = FRONTEND / "src" / "api"
    for path in _files(FRONTEND / "src"):
        if api_dir in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        assert "fetch(" not in text, str(path)
        assert "EventSource(" not in text, str(path)
