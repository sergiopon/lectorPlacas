from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lector_placas.domain.entities import ReviewStatus
from lector_placas.domain.errors import UnsafePathError
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import fake_sighting_record
from tests.unit.web.conftest import FakeRunner, authenticated_client, make_session

JOB = {"video": "videos/v.mp4", "profile": "calle_lenta"}


@pytest.fixture
def web(config: AppConfig, fake_runner: FakeRunner, tmp_path: Path) -> Iterator[TestClient]:
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "v.mp4").write_bytes(b"synthetic")
    with authenticated_client(config.model_copy(update={"root_dir": tmp_path}), fake_runner) as c:
        yield c


@pytest.fixture(autouse=True)
def patch_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    def validated(config: AppConfig, path: Path) -> Path:
        return path.resolve()

    monkeypatch.setattr("lector_placas.web.routes_actions.composition.validated_video", validated)


def wait_state(client: TestClient, job_id: str, state: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    body: dict[str, object] = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] == state:
            break
        time.sleep(0.02)
    return body


def test_start_job_and_poll(web: TestClient, fake_runner: FakeRunner) -> None:
    response = web.post("/api/jobs", json=JOB)
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "running"
    fake_runner.go.set()
    final = wait_state(web, body["jobId"], "completed")
    assert final["state"] == "completed"
    assert final["runId"] == 7


def test_start_job_errors(
    web: TestClient, fake_runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_profile = web.post("/api/jobs", json={"video": "videos/v.mp4", "profile": "autopista"})
    assert bad_profile.status_code == 422
    assert bad_profile.json() == {"detail": "perfil desconocido"}

    def unsafe(config: AppConfig, path: Path) -> Path:
        raise UnsafePathError("fuera")

    with monkeypatch.context() as patch:
        patch.setattr("lector_placas.web.routes_actions.composition.validated_video", unsafe)
        invalid = web.post("/api/jobs", json=JOB)
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "video no válido"}
    first = web.post("/api/jobs", json=JOB)
    assert first.status_code == 202
    assert web.post("/api/jobs", json=JOB).status_code == 409
    fake_runner.go.set()
    wait_state(web, first.json()["jobId"], "completed")


def test_events_stream(web: TestClient, fake_runner: FakeRunner) -> None:
    job_id = web.post("/api/jobs", json=JOB).json()["jobId"]
    fake_runner.go.set()
    response = web.get(f"/api/jobs/{job_id}/events")
    assert response.headers["content-type"].startswith("text/event-stream")
    last = [chunk for chunk in response.text.split("\n\n") if chunk.strip()][-1]
    assert last.startswith("event: done")
    assert '"state":"completed"' in last


def test_cancel_job(web: TestClient, fake_runner: FakeRunner) -> None:
    job_id = web.post("/api/jobs", json=JOB).json()["jobId"]
    assert web.post(f"/api/jobs/{job_id}/cancel").status_code == 202
    fake_runner.go.set()
    assert wait_state(web, job_id, "cancelled")["state"] == "cancelled"


def test_decision(web: TestClient) -> None:
    repo = make_session.repository  # type: ignore[attr-defined]
    repo.records[1] = fake_sighting_record(
        sighting_id=1, status=ReviewStatus.UNVERIFIED, plate_text="ABC123"
    )
    ok = web.post(
        "/api/sightings/1/decision", json={"action": "correct", "correctedText": "xyz98l"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "corrected"
    assert ok.json()["plateText"] == "XYZ98L"
    missing_text = web.post("/api/sightings/1/decision", json={"action": "correct"})
    assert missing_text.status_code == 422
    assert missing_text.json() == {"detail": "decisión inválida"}
    assert web.post("/api/sightings/999/decision", json={"action": "confirm"}).status_code == 404


def test_export_purge_metrics(web: TestClient) -> None:
    empty = web.get("/api/metrics")
    assert empty.status_code == 404
    assert empty.json() == {"detail": "no hay avistamientos para evaluar"}
    repo = make_session.repository  # type: ignore[attr-defined]
    repo.records[1] = fake_sighting_record(sighting_id=1)
    export = web.post("/api/export", json={})
    assert export.status_code == 200
    assert export.json() == {"file": "sightings-1.csv"}
    purge = web.post("/api/purge")
    assert purge.status_code == 200
    assert set(purge.json()) == {
        "cropsDeleted",
        "sightingsDeleted",
        "runsDeleted",
        "platesDeleted",
        "exportsDeleted",
        "trainingDeleted",
    }
    metrics = web.get("/api/metrics")
    assert metrics.status_code == 200
    assert {"precisionConfirmed", "cer", "reasonCounts", "confirmedIllegible"} <= set(
        metrics.json()
    )


def test_unknown_job_404(web: TestClient) -> None:
    expected = {"detail": "trabajo no encontrado"}
    for response in (
        web.get("/api/jobs/x"),
        web.post("/api/jobs/x/cancel"),
        web.get("/api/jobs/x/events"),
    ):
        assert response.status_code == 404
        assert response.json() == expected
