from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.factory import create_app
from lector_placas.web.security import CSP, SessionAuth, allowed_hosts_for
from tests.fixtures.fakes import FakeKeyProvider
from tests.unit.web.conftest import make_session


def static_client(config: AppConfig, static_dir: Path) -> TestClient:
    app = create_app(
        config,
        FakeKeyProvider(),
        SessionAuth("arranque"),
        allowed_hosts_for(8765),
        session_factory=make_session,
        static_dir=static_dir,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    client.get("/auth", params={"token": "arranque"}, follow_redirects=False)
    return client


def check_index_and_headers(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200
    assert index.text == "<p>hola</p>"
    assert index.headers["content-security-policy"] == CSP
    assert index.headers["referrer-policy"] == "no-referrer"
    assert index.headers["x-content-type-options"] == "nosniff"


def test_serves_built_frontend(config: AppConfig, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<p>hola</p>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    with static_client(config, dist) as client:
        check_index_and_headers(client)
        asset = client.get("/assets/a.js")
        assert asset.status_code == 200
        assert asset.text == "console.log(1)"
        assert client.get("/api/health").status_code == 200


def test_without_frontend(config: AppConfig, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    with static_client(config, dist) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Frontend no compilado" in response.text
