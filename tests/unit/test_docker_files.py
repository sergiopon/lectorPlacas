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


def test_dockerfile_runs_as_non_root_user() -> None:
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert "USER lector" in lines
    fetch_index = next(i for i, line in enumerate(lines) if "lector models fetch" in line)
    assert lines.index("USER lector") < fetch_index
    assert not any("0777" in line or "/run/secrets" in line for line in lines)
    env_line = next(line for line in lines if line.startswith("ENV"))
    assert "LECTOR_KEY_FILE=/app/keys/lector_key" in env_line
    assert "LECTOR_EXECUTION_PROVIDER=cpu" in env_line


def test_compose_uses_named_volumes() -> None:
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert all("user" not in service for service in data["services"].values())
    assert "secrets" not in data
    assert set(data["volumes"]) == {"lector-data", "lector-logs", "lector-keys"}
    assert data["services"]["lector"]["volumes"] == [
        "${LECTOR_VIDEOS_DIR:-./videos}:/app/videos:ro",
        "lector-data:/app/data",
        "lector-logs:/app/logs",
        "lector-keys:/app/keys",
    ]


def test_compose_execution_provider() -> None:
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert data["services"]["lector"]["environment"] == {"LECTOR_EXECUTION_PROVIDER": "cpu"}
    assert data["services"]["lector-gpu"]["environment"] == {"LECTOR_EXECUTION_PROVIDER": "cuda"}


def test_gitattributes_forces_lf() -> None:
    lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert lines == ["* text=auto eol=lf", "*.png binary"]
