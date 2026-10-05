from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.domain.errors import ConfigurationError
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config" / "lector.yaml"


def test_env_overrides_execution_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_EXECUTION_PROVIDER", "cpu")
    assert load_config(CONFIG).inference.execution_provider == "cpu"
    monkeypatch.setenv("LECTOR_EXECUTION_PROVIDER", "cuda")
    assert load_config(CONFIG).inference.execution_provider == "cuda"


def test_env_absent_keeps_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LECTOR_EXECUTION_PROVIDER", raising=False)
    assert load_config(CONFIG).inference.execution_provider == "cuda"


def test_env_empty_keeps_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_EXECUTION_PROVIDER", "")
    assert load_config(CONFIG).inference.execution_provider == "cuda"


def test_env_invalid_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("rocm", "CPU"):
        monkeypatch.setenv("LECTOR_EXECUTION_PROVIDER", value)
        with pytest.raises(ConfigurationError) as info:
            load_config(CONFIG)
        assert str(info.value) == "LECTOR_EXECUTION_PROVIDER debe ser 'cpu' o 'cuda'"
