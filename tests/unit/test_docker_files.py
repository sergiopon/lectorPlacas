from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_pins_digests() -> None:
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    checked = [line for line in lines if line.startswith("FROM") or "COPY --from=ghcr.io" in line]
    assert len(checked) == 3
    assert all("@sha256:" in line for line in checked)


def test_compose_publishes_loopback_only() -> None:
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    for service in data["services"].values():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:")


def test_dockerignore_excludes_private_data() -> None:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for name in ("data", "videos", "models", "secrets", "CLAUDE.md", "CONTEXT.md"):
        assert name in lines
    assert "docs/05-orquestacion.md" in lines
