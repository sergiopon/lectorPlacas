from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QThread, QTimer

from lector_placas.application.ports import ProgressUpdate, RunStats
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.errors import ProcessingCancelledError, VideoSourceError
from lector_placas.gui import processing
from lector_placas.gui.processing import ProcessingRequest, ProcessingWorker, QtProgressReporter
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import FakeKeyProvider

GENERIC_MESSAGE = "error inesperado; revise logs/lector.log"


def _stats() -> RunStats:
    return RunStats(10, 8, 3, 2, 1, 0, 500, 1000)


class _FakeRepository:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeUseCase:
    def __init__(self, error: VideoSourceError | None = None, runtime_error: bool = False) -> None:
        self.result = RunResult(7, _stats())
        self.error = error
        self.runtime_error = runtime_error
        self.cancel_trigger: Callable[[], None] | None = None

    def execute(self, video: Path, sha: str, progress: QtProgressReporter) -> RunResult:
        for _ in range(3):
            progress.report(ProgressUpdate(1, 1, 100, 100, 1))
            if self.cancel_trigger is not None:
                self.cancel_trigger()
                self.cancel_trigger = None
            if progress.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
        if self.error is not None:
            raise self.error
        if self.runtime_error:
            raise RuntimeError("boom")
        return self.result


def _patch_composition(
    monkeypatch, repository: _FakeRepository, thread_ids: list[int], use_case: _FakeUseCase
) -> None:
    """Configura los mocks de composición para el worker."""
    monkeypatch.setattr(
        composition,
        "build_repository",
        lambda c, k: thread_ids.append(threading.get_ident()) or repository,
    )
    monkeypatch.setattr(composition, "build_crop_store", lambda c, k: object())
    monkeypatch.setattr(
        composition,
        "build_process_video",
        lambda c, profile, repo, crop_store, clock: use_case,
    )
    monkeypatch.setattr(processing, "sha256_file", lambda path: "a" * 64)


def _connect_worker_signals(worker: ProcessingWorker, events: list[tuple[str, object]]) -> None:
    """Conecta las señales del worker para registrar eventos."""
    worker.progress.connect(lambda update: events.append(("progress", update)))
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.cancelled.connect(lambda: events.append(("cancelled", None)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))


def _run_worker_in_thread(worker: ProcessingWorker) -> None:
    """Ejecuta el worker en un QThread hasta que termine."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    thread.start()
    loop.exec()
    thread.wait(5000)


def _run_worker(
    config: AppConfig,
    monkeypatch,
    use_case: _FakeUseCase,
    cancel_during: bool = False,
) -> tuple[list[tuple[str, object]], list[int], _FakeRepository]:
    repository = _FakeRepository()
    thread_ids: list[int] = []
    _patch_composition(monkeypatch, repository, thread_ids, use_case)
    worker = ProcessingWorker(
        config, FakeKeyProvider(), ProcessingRequest(Path("/videos/ok.mp4"), "calle_lenta")
    )
    if cancel_during:
        use_case.cancel_trigger = worker.request_cancel
    events: list[tuple[str, object]] = []
    _connect_worker_signals(worker, events)
    _run_worker_in_thread(worker)
    return events, thread_ids, repository


def _kinds(events: list[tuple[str, object]]) -> list[str]:
    return [kind for kind, _ in events]


def test_reporter_throttles_by_interval() -> None:
    emitted: list[ProgressUpdate] = []
    clock = iter([0.0, 0.05, 0.12]).__next__
    reporter = QtProgressReporter(emitted.append, clock)
    for _ in range(3):
        reporter.report(ProgressUpdate(1, 1, 100, 100, 1))
    assert len(emitted) == 2


def test_reporter_cancel_flag() -> None:
    reporter = QtProgressReporter(lambda update: None)
    assert reporter.cancel_requested() is False
    reporter.request_cancel()
    assert reporter.cancel_requested() is True


def test_worker_success_emits_progress_succeeded_finished(
    config: AppConfig, monkeypatch, qapp
) -> None:
    events, _, repository = _run_worker(config, monkeypatch, _FakeUseCase())
    kinds = _kinds(events)
    assert "progress" in kinds
    assert "succeeded" in kinds
    assert "finished" in kinds
    assert "cancelled" not in kinds
    assert "failed" not in kinds
    assert kinds.index("succeeded") < kinds.index("finished")
    assert repository.closed is True


def test_worker_cancel_emits_cancelled(config: AppConfig, monkeypatch, qapp) -> None:
    events, _, _repository = _run_worker(config, monkeypatch, _FakeUseCase(), cancel_during=True)
    kinds = _kinds(events)
    assert "cancelled" in kinds
    assert "finished" in kinds
    assert "succeeded" not in kinds
    assert "failed" not in kinds


def test_worker_domain_error_emits_failed_message(config: AppConfig, monkeypatch, qapp) -> None:
    events, _, _repository = _run_worker(
        config, monkeypatch, _FakeUseCase(error=VideoSourceError("video dañado"))
    )
    failed = [message for kind, message in events if kind == "failed"]
    assert failed == ["video dañado"]
    assert "finished" in _kinds(events)


def test_worker_unexpected_error_emits_generic_message(
    config: AppConfig, monkeypatch, qapp
) -> None:
    events, _, _repository = _run_worker(config, monkeypatch, _FakeUseCase(runtime_error=True))
    failed = [message for kind, message in events if kind == "failed"]
    assert failed == [GENERIC_MESSAGE]
    assert "finished" in _kinds(events)


def test_worker_builds_repository_in_worker_thread(config: AppConfig, monkeypatch, qapp) -> None:
    events, thread_ids, _repository = _run_worker(config, monkeypatch, _FakeUseCase())
    assert "finished" in _kinds(events)
    assert len(thread_ids) == 1
    assert thread_ids[0] != threading.get_ident()


@pytest.mark.parametrize(
    ("use_case_factory", "cancel_during"),
    [
        (_FakeUseCase, False),
        (_FakeUseCase, True),
        (lambda: _FakeUseCase(error=VideoSourceError("video dañado")), False),
        (lambda: _FakeUseCase(runtime_error=True), False),
    ],
    ids=["success", "cancelled", "domain_error", "unexpected_error"],
)
def test_worker_closes_repository_on_every_outcome(
    config: AppConfig,
    monkeypatch,
    qapp,
    use_case_factory: Callable[[], _FakeUseCase],
    cancel_during: bool,
) -> None:
    events, _, repository = _run_worker(
        config, monkeypatch, use_case_factory(), cancel_during=cancel_during
    )
    assert "finished" in _kinds(events)
    assert repository.closed is True
