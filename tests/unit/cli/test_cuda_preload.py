"""La precarga de CUDA ocurre en todos los caminos que crean sesiones ONNX (corrección de evaluate-*)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from lector_placas.adapters.inference import onnx_session
from lector_placas.cli import composition


class FakeRegistry:
    def verified_path(self, model_id: str) -> Path:
        return Path(model_id)


def _config(backend: str = "open_image_models") -> Any:
    return SimpleNamespace(
        inference=SimpleNamespace(execution_provider="cuda"),
        models=SimpleNamespace(
            ocr=SimpleNamespace(model_id="ocr", config_id="ocr-config"),
            plate_detector=SimpleNamespace(
                backend=backend, model_id="det", score_threshold=0.25, input_size=384
            ),
        ),
    )


def test_ensure_cuda_libraries_preloads_only_for_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(onnx_session, "_preload_cuda_libraries", lambda: calls.append("preload"))
    onnx_session.ensure_cuda_libraries("cpu")
    assert calls == []
    onnx_session.ensure_cuda_libraries("cuda")
    assert calls == ["preload"]


def test_build_reader_preloads_before_creating_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        composition, "ensure_cuda_libraries", lambda ep: order.append(f"preload:{ep}")
    )
    monkeypatch.setattr(
        composition,
        "create_fast_plate_ocr_reader",
        lambda *a, **k: order.append("reader") or "reader",
    )
    assert composition.build_reader(_config(), FakeRegistry()) == "reader"  # type: ignore[arg-type]
    assert order == ["preload:cuda", "reader"]


def test_build_oim_plate_detector_preloads_before_creating_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        composition, "ensure_cuda_libraries", lambda ep: order.append(f"preload:{ep}")
    )
    monkeypatch.setattr(
        composition,
        "create_oim_plate_detector",
        lambda *a, **k: order.append("detector") or "detector",
    )
    assert composition.build_plate_detector(_config(), FakeRegistry()) == "detector"  # type: ignore[arg-type]
    assert order == ["preload:cuda", "detector"]
