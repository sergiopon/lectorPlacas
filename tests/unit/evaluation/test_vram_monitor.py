from __future__ import annotations

import io
import subprocess

import pytest

from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.vram_monitor import VramMonitor, parse_mib


class FakeProcess:
    def __init__(self, text: str) -> None:
        self.stdout = io.StringIO(text)
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        return 0


def fake_run(stdout: str):  # type: ignore[no-untyped-def]
    def run(args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args, 0, stdout=stdout)

    return run


def test_parse_mib() -> None:
    assert parse_mib(" 1500 \n") == 1500
    assert parse_mib("N/A") is None


def test_peak_above_baseline() -> None:
    process = FakeProcess("1000\n1500\nN/A\n1200\n")
    with VramMonitor(run=fake_run("800\n"), popen=lambda *a, **k: process) as monitor:
        pass
    assert monitor.peak_mib == 700
    assert process.terminated


def test_missing_nvidia_smi() -> None:
    def missing(args, **kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("nvidia-smi")

    with pytest.raises(EvaluationError), VramMonitor(run=missing):
        pass
