# tests/unit/infrastructure/test_model_fetcher.py
from __future__ import annotations

import hashlib
import io
import stat
from pathlib import Path
from typing import BinaryIO

import pytest
import yaml

from lector_placas.domain.errors import ModelFetchError
from lector_placas.infrastructure.model_fetcher import fetch_models

CONTENT = b"pesos sinteticos" * 1000
URL = "https://github.com/example/releases/download/v1/m.onnx"


def manifest(tmp_path: Path, content: bytes = CONTENT, url: str = URL) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "models": [
                    {
                        "model_id": "m-uno",
                        "filename": "m.onnx",
                        "url": url,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size_bytes": len(content),
                        "license": "MIT",
                        "source": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class Opener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> BinaryIO:
        self.calls.append(url)
        return io.BytesIO(self.payload)


def test_downloads_verifies_and_skips_existing(tmp_path: Path) -> None:
    opener = Opener(CONTENT)
    models = tmp_path / "models"
    assert fetch_models(manifest(tmp_path), models, opener) == ["m-uno"]
    assert (models / "m-uno" / "m.onnx").read_bytes() == CONTENT
    assert stat.S_IMODE((models / "m-uno").stat().st_mode) == 0o700
    assert fetch_models(manifest(tmp_path), models, opener) == []
    assert opener.calls == [URL]


def test_hash_mismatch_leaves_nothing(tmp_path: Path) -> None:
    models = tmp_path / "models"
    with pytest.raises(ModelFetchError):
        fetch_models(manifest(tmp_path), models, Opener(b"otra cosa"))
    assert not list((models / "m-uno").glob("*"))


def test_pending_or_null_url_entries_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "models": [
                    {
                        "model_id": "local",
                        "filename": "x.onnx",
                        "url": None,
                        "sha256": "PENDIENTE_EXPORT",
                        "size_bytes": 0,
                        "license": "AGPL-3.0",
                        "source": "local",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert fetch_models(path, tmp_path / "models", Opener(b"")) == []
