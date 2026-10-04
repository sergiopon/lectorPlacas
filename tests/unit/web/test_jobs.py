from __future__ import annotations

import time
from pathlib import Path

import pytest

from lector_placas.application.ports import ProgressReporter, ProgressUpdate
from lector_placas.domain.errors import RepositoryError
from lector_placas.web.jobs import (
    GENERIC_ERROR_MESSAGE,
    JobBusyError,
    JobManager,
    JobNotFoundError,
    JobReporter,
    JobSnapshot,
)
from tests.unit.web.conftest import FakeRunner

VIDEO = Path("v.mp4")


def wait_not_running(manager: JobManager, job_id: str) -> JobSnapshot:
    deadline = time.monotonic() + 5
    snap = manager.snapshot(job_id)
    while snap.state == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        snap = manager.snapshot(job_id)
    return snap


def test_job_completes() -> None:
    def runner(video: Path, profile: str, reporter: ProgressReporter) -> int:
        return 7

    manager = JobManager(runner)
    snap = wait_not_running(manager, manager.start(VIDEO, "calle_lenta"))
    assert snap.state == "completed"
    assert snap.run_id == 7


def test_job_cancelled(fake_runner: FakeRunner) -> None:
    manager = JobManager(fake_runner)
    job_id = manager.start(VIDEO, "calle_lenta")
    manager.cancel(job_id)
    fake_runner.go.set()
    snap = wait_not_running(manager, job_id)
    assert snap.state == "cancelled"
    assert snap.message == "procesamiento cancelado"


def test_job_failed_domain_and_unexpected() -> None:
    def domain_error(video: Path, profile: str, reporter: ProgressReporter) -> int:
        raise RepositoryError("fallo")

    def unexpected_error(video: Path, profile: str, reporter: ProgressReporter) -> int:
        raise RuntimeError("secreto")

    first = JobManager(domain_error)
    snap = wait_not_running(first, first.start(VIDEO, "calle_lenta"))
    assert snap.state == "failed"
    assert snap.message == "fallo"
    second = JobManager(unexpected_error)
    snap = wait_not_running(second, second.start(VIDEO, "calle_lenta"))
    assert snap.state == "failed"
    assert snap.message == GENERIC_ERROR_MESSAGE


def test_only_one_job(fake_runner: FakeRunner) -> None:
    manager = JobManager(fake_runner)
    job_id = manager.start(VIDEO, "calle_lenta")
    with pytest.raises(JobBusyError):
        manager.start(VIDEO, "calle_lenta")
    fake_runner.go.set()
    wait_not_running(manager, job_id)


def test_unknown_job() -> None:
    manager = JobManager(FakeRunner())
    with pytest.raises(JobNotFoundError):
        manager.snapshot("x")
    with pytest.raises(JobNotFoundError):
        manager.cancel("x")


def test_reporter_latest() -> None:
    reporter = JobReporter()
    assert reporter.latest() is None
    update = ProgressUpdate(1, 1, 100, 1000, 0)
    reporter.report(update)
    assert reporter.latest() == update
