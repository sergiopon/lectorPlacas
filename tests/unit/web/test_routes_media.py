from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import av
import numpy as np
from fastapi.testclient import TestClient

from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory
from lector_placas.application.ports import ImageBGR, RunStart, VideoInfo
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason
from lector_placas.domain.errors import VideoSourceError
from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.media import MediaServices, VideoLocator
from tests.fixtures.fakes import fake_sighting_record
from tests.unit.web.conftest import authenticated_client, make_session


def make_video(path: Path) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for index in range(30):
            image = np.full((48, 64, 3), index * 8, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


class FakeGrabber:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, int]] = []
        self.fail = False

    def grab(self, path: Path, timestamp_ms: int) -> ImageBGR:
        self.calls.append((path, timestamp_ms))
        if self.fail:
            raise VideoSourceError("fallo")
        return np.zeros((48, 64, 3), dtype=np.uint8)


def add(sighting_id: int, **kwargs: object) -> None:
    repo = make_session.repository  # type: ignore[attr-defined]
    repo.records[sighting_id] = fake_sighting_record(sighting_id=sighting_id, **kwargs)


def setup_media(c: TestClient, config: AppConfig, video: Path) -> FakeGrabber:
    grabber = FakeGrabber()
    c.app.state.media = MediaServices(  # type: ignore[attr-defined]
        VideoLocator(config), grabber, PyAVVideoSourceFactory()
    )
    repo = make_session.repository  # type: ignore[attr-defined]
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    started = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    repo.start_run(RunStart(sha, "calle_lenta", VideoInfo(64, 48, 0, 3000, 10.0, "mpeg4"), started))
    return grabber


def test_video_full_and_range(config: AppConfig, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    video = make_video(folder / "v.mp4")
    cfg = config.model_copy(update={"root_dir": tmp_path})
    with authenticated_client(cfg) as c:
        setup_media(c, cfg, video)
        response = c.get("/api/runs/1/video")
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"
        assert response.content == video.read_bytes()
        assert "content-disposition" not in response.headers
        partial = c.get("/api/runs/1/video", headers={"Range": "bytes=0-99"})
        assert partial.status_code == 206
        assert len(partial.content) == 100
        missing = c.get("/api/runs/2/video")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "video no disponible"}


def check_404(c: TestClient, route: str, detail: str) -> None:
    response = c.get(route)
    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_frame(config: AppConfig, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    video = make_video(folder / "v.mp4")
    cfg = config.model_copy(update={"root_dir": tmp_path})
    with authenticated_client(cfg) as c:
        grabber = setup_media(c, cfg, video)
        add(1, run_id=1, first_seen_ms=1000, last_seen_ms=2000)
        response = c.get("/api/sightings/1/frame")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-frame-timestamp-ms"] == "1500"
        assert grabber.calls[-1][1] == 1500
        check_404(c, "/api/sightings/99/frame", "avistamiento no encontrado")
        grabber.fail = True
        check_404(c, "/api/sightings/1/frame", "fotograma no disponible")
        grabber.fail = False
        video.unlink()
        check_404(c, "/api/sightings/1/frame", "video no disponible")


def test_counts(client: TestClient) -> None:
    add(1, status=ReviewStatus.CONFIRMED)
    add(2, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.LOW_CONFIDENCE,))
    add(3, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.PREDICTED_ILLEGIBLE,))
    add(4, status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.PREDICTED_NOT_PLATE,))
    assert client.get("/api/sighting-counts").json() == {
        "unverified": 1,
        "confirmed": 1,
        "corrected": 0,
        "rejected": 0,
        "illegible": 0,
        "all": 2,
        "hidden": 2,
    }
    invalid = client.get("/api/sighting-counts", params={"q": "Ñ"})
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "parámetro inválido"}


def test_metrics_by_run(client: TestClient) -> None:
    assert client.get("/api/metrics/runs").json() == []
    add(1, run_id=2, status=ReviewStatus.CONFIRMED)
    add(2, run_id=1, status=ReviewStatus.CORRECTED)
    add(3, run_id=1, status=ReviewStatus.REJECTED)
    body = client.get("/api/metrics/runs").json()
    assert [item["runId"] for item in body] == [1, 2]
    assert all(
        set(item) == {"runId", "legible", "illegible", "rejected", "precision", "cer"}
        for item in body
    )


def test_settings(client: TestClient, config: AppConfig) -> None:
    assert client.get("/api/settings").json() == {
        "cropsDays": config.retention.crops_days,
        "recordsDays": config.retention.records_days,
        "trainingDays": config.retention.training_days,
    }


def test_media_requires_session(client: TestClient) -> None:
    client.cookies.clear()
    for route in (
        "/api/runs/1/video",
        "/api/sightings/1/frame",
        "/api/sighting-counts",
        "/api/metrics/runs",
        "/api/settings",
    ):
        assert client.get(route).status_code == 401
