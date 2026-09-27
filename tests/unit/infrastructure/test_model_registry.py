# tests/unit/infrastructure/test_model_registry.py
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from lector_placas.domain.errors import ConfigurationError, ModelIntegrityError
from lector_placas.infrastructure.model_registry import ManifestModelRegistry, load_manifest

ROOT = Path(__file__).resolve().parents[3]
CONTENT = b"modelo sintetico"


def write_manifest(tmp_path: Path, **overrides: object) -> Path:
    entry = {
        "model_id": "m-uno",
        "filename": "m.onnx",
        "url": None,
        "sha256": hashlib.sha256(CONTENT).hexdigest(),
        "size_bytes": len(CONTENT),
        "license": "MIT",
        "source": "test",
    }
    entry.update(overrides)
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [entry]}), encoding="utf-8")
    return path


def test_real_manifest_is_valid() -> None:
    manifest = load_manifest(ROOT / "config" / "models.yaml")
    assert manifest.entry("fpo-cct-xs-v2-global").sha256.startswith("8031afb5")
    assert manifest.entry("fpo-cct-xs-v2-colombia").sha256.startswith("2a057dd8")


def test_verified_path_ok_and_tampered(tmp_path: Path) -> None:
    models = tmp_path / "models"
    (models / "m-uno").mkdir(parents=True)
    target = models / "m-uno" / "m.onnx"
    target.write_bytes(CONTENT)
    registry = ManifestModelRegistry(write_manifest(tmp_path), models)
    assert registry.verified_path("m-uno") == target.resolve()
    target.write_bytes(b"alterado")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("m-uno")


def test_missing_unknown_and_pending(tmp_path: Path) -> None:
    registry = ManifestModelRegistry(write_manifest(tmp_path), tmp_path / "models")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("m-uno")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("otro")
    pending = ManifestModelRegistry(write_manifest(tmp_path, sha256="PENDIENTE_EXPORT"), tmp_path)
    with pytest.raises(ModelIntegrityError):
        pending.verified_path("m-uno")


@pytest.mark.parametrize(
    "overrides",
    [
        {"filename": "../x.onnx"},
        {"filename": "a/b.onnx"},
        {"url": "http://example.com/m"},
        {"sha256": "abc"},
        {"model_id": "Mayus"},
        {"size_bytes": -1},
    ],
)
def test_invalid_manifest(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        load_manifest(write_manifest(tmp_path, **overrides))
