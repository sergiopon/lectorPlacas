from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lector_placas.cli import composition
from lector_placas.cli import main as cli_main
from lector_placas.infrastructure import network_guard
from tests.fixtures.fakes import FakeKeyProvider

ROOT = Path(__file__).resolve().parents[3]


class RecordingKeyProvider(FakeKeyProvider):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def master_key(self) -> bytes:
        self.events.append("key")
        return super().master_key()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[bool]]:
    events: list[str] = []
    builds: list[bool] = []

    def build(create_if_missing: bool) -> RecordingKeyProvider:
        builds.append(create_if_missing)
        return RecordingKeyProvider(events)

    monkeypatch.setattr(composition, "build_key_provider", build)
    monkeypatch.setattr(network_guard, "block_network", lambda: events.append("block"))
    return events, builds


def run(project: Path, *args: str) -> int:
    return cli_main.main(["--config", str(project / "config" / "lector.yaml"), *args])


def test_key_init_reads_key_before_blocking_network(project, recorded) -> None:
    events, builds = recorded
    assert run(project, "key", "init") == 0
    assert builds == [True]
    assert events[:2] == ["key", "block"]


def test_commands_without_key_do_not_touch_keyring(project, recorded) -> None:
    events, builds = recorded
    run(project, "models", "verify")
    assert builds == []
    assert "key" not in events


@pytest.mark.integration
def test_purge_reuses_prefetched_provider(project, recorded) -> None:
    events, builds = recorded
    assert run(project, "purge") == 0
    assert builds == [False]
    assert events.index("key") < events.index("block")
