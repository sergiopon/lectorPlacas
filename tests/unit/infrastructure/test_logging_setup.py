from __future__ import annotations

import logging
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from lector_placas.domain.errors import ConfigurationError
from lector_placas.infrastructure.logging_setup import (
    HANDLER_MARK,
    configure_logging,
    redact_plates,
)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARK, False):
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("placa ABC123 leída", "placa A****3 leída"),
        ("moto XYZ98K", "moto X****K"),
        ("motocarro 123ABC", "motocarro 1****C"),
        ("diplomática CD1234", "diplomática C****4"),
        ("remolque R12345", "remolque R****5"),
        ("temporal T1234", "temporal T***4"),
        ("run_id=12 frames=300", "run_id=12 frames=300"),
        ("abc123", "abc123"),
        ("XABC1234", "XABC1234"),
    ],
)
def test_redact_plates(text: str, expected: str) -> None:
    assert redact_plates(text) == expected


def test_configure_logging_writes_redacted_private_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "lector.log"
    configure_logging("INFO", log_file)
    configure_logging("INFO", log_file)
    logger = logging.getLogger("lector_placas.test")
    logger.info("placa %s detectada", "ABC123")
    try:
        raise ValueError("fallo con XYZ98K")
    except ValueError:
        logger.exception("error")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "ABC123" not in content and "XYZ98K" not in content
    assert "A****3" in content and "X****K" in content
    assert content.count("placa A****3 detectada") == 1
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(log_file.parent.stat().st_mode) == 0o700


def test_invalid_level() -> None:
    with pytest.raises(ConfigurationError):
        configure_logging("VERBOSE", Path("/tmp/no-importa.log"))
