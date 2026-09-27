from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lector_placas.infrastructure.config import AppConfig, load_config

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def config() -> AppConfig:
    return load_config(ROOT / "config" / "lector.yaml")
