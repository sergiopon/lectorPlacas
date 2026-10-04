from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from lector_placas.application.ports import RunStart, RunStats, VideoInfo
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import fake_sighting_record
from tests.unit.web.conftest import authenticated_client, make_session


def add(sighting_id: int, **kwargs: object) -> None:
    repo = make_session.repository  # type: ignore[attr-defined]
    repo.records[sighting_id] = fake_sighting_record(sighting_id=sighting_id, **kwargs)


def test_profiles(client: TestClient, config: AppConfig) -> None:
    body = client.get("/api/profiles").json()
    assert [p["name"] for p in body] == list(config.profiles)
    assert len(body) == 4
    by_name = {p["name"]: p for p in body}
    assert by_name["calle_lenta"]["default"] is True
    assert by_name["patrulla"]["mode"] == "movil"
    assert by_name["patrulla"]["label"] == "Patrulla"
    assert all(set(p) == {"name", "label", "description", "mode", "default"} for p in body)


def test_videos_lists_allowed_files(config: AppConfig, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.mp4").write_bytes(b"abc")
    (folder / "b.txt").write_bytes(b"x")
    (folder / "sub" / "c.mp4").write_bytes(b"x")
    with authenticated_client(config.model_copy(update={"root_dir": tmp_path})) as c:
        assert c.get("/api/videos").json() == [
            {"name": "a.mp4", "path": "videos/a.mp4", "sizeBytes": 3}
        ]


def test_sightings_page_and_fields(client: TestClient) -> None:
    crop = np.zeros((4, 6, 3), np.uint8)
    ref = make_session.crop_store.save(crop)  # type: ignore[attr-defined]
    add(1)
    add(2, crop_ref=ref)
    add(3)
    body = client.get("/api/sightings").json()
    assert body["total"] == 3
    assert body["pageSize"] == 48
    assert [i["id"] for i in body["items"]] == [3, 2, 1]
    item = body["items"][1]
    assert item["cropUrl"] == "/api/sightings/2/crop"
    assert item["hiddenLowQuality"] is False
    assert item["duplicates"] == 0
    for key in (
        "runId",
        "plateText",
        "ocrText",
        "numReadings",
        "firstSeenMs",
        "lastSeenMs",
        "reviewedAt",
    ):
        assert key in item


def test_sightings_filters(client: TestClient) -> None:
    add(1, status=ReviewStatus.CONFIRMED, plate_text="ABC123")
    add(2, status=ReviewStatus.UNVERIFIED, plate_text="XYZ987")
    confirmed = client.get("/api/sightings", params={"status": "confirmed"}).json()
    assert [i["id"] for i in confirmed["items"]] == [1]
    prefixed = client.get("/api/sightings", params={"q": "abc"}).json()
    assert [i["id"] for i in prefixed["items"]] == [1]
    for params in ({"q": "AB-1"}, {"status": "otro"}, {"page": 0}):
        response = client.get("/api/sightings", params=params)
        assert response.status_code == 422
        assert response.json() == {"detail": "parámetro inválido"}


def test_duplicates_hidden_and_counted(client: TestClient) -> None:
    add(1)
    add(2)
    make_session.repository.mark_duplicates([(2, 1)])  # type: ignore[attr-defined]
    default = client.get("/api/sightings").json()
    assert [i["id"] for i in default["items"]] == [1]
    assert default["items"][0]["duplicates"] == 1
    both = client.get("/api/sightings", params={"duplicates": "true"}).json()
    assert [i["id"] for i in both["items"]] == [2, 1]
    assert both["items"][0]["duplicateOf"] == 1


def test_sighting_detail_and_404(client: TestClient) -> None:
    add(1)
    assert client.get("/api/sightings/1").json()["id"] == 1
    missing = client.get("/api/sightings/999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "avistamiento no encontrado"}


def test_crop_png_in_memory(client: TestClient) -> None:
    image = np.random.default_rng(0).integers(0, 255, (5, 7, 3), dtype=np.uint8)
    ref = make_session.crop_store.save(image)  # type: ignore[attr-defined]
    add(1, crop_ref=ref)
    add(2)
    response = client.get("/api/sightings/1/crop")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    decoded = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(decoded, image)
    missing = client.get("/api/sightings/2/crop")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "recorte no disponible"}


def test_runs_and_summary(client: TestClient) -> None:
    repo = make_session.repository  # type: ignore[attr-defined]
    started = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    run_id = repo.start_run(
        RunStart("a" * 64, "calle_lenta", VideoInfo(640, 480, 0, 10000, 10.0, "h264"), started)
    )
    repo.finish_run(run_id, RunStats(10, 10, 4, 2, 1, 1, 5000, 10000), started, True)
    add(1, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.LOW_CONFIDENCE,))
    add(2, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,))
    add(3, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.PREDICTED_NOT_PLATE,))
    item = client.get("/api/runs").json()["items"][0]
    assert item["video"] == "Video 1"
    assert item["speedFactor"] == 2.0
    assert item["vehicles"] == 4
    assert item["mode"] == "estatico"
    assert client.get("/api/summary").json() == {"pending": 1, "hidden": 2}


def test_hidden_filter(client: TestClient) -> None:
    add(1, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,))
    add(2, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.LOW_CONFIDENCE,))
    default = client.get("/api/sightings").json()
    assert [i["id"] for i in default["items"]] == [2]
    only = client.get("/api/sightings", params={"hidden": "true"}).json()
    assert [i["id"] for i in only["items"]] == [1]
    assert only["items"][0]["hiddenLowQuality"] is True
    everything = client.get("/api/sightings", params={"hidden": "all"}).json()
    assert [i["id"] for i in everything["items"]] == [2, 1]
    assert client.get("/api/sightings", params={"hidden": "x"}).status_code == 422
