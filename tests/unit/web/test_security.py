from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.factory import create_app
from lector_placas.web.security import CSP, SessionAuth, allowed_hosts_for
from tests.fixtures.fakes import FakeKeyProvider
from tests.unit.web.conftest import make_session


def anonymous_client(config: AppConfig) -> TestClient:
    app = create_app(
        config,
        FakeKeyProvider(),
        SessionAuth("arranque"),
        allowed_hosts_for(8765),
        session_factory=make_session,
    )
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_auth_exchanges_token_once(config: AppConfig) -> None:
    with anonymous_client(config) as c:
        first = c.get("/auth", params={"token": "arranque"}, follow_redirects=False)
        assert first.status_code == 303
        assert first.headers["location"] == "/"
        cookie = first.headers["set-cookie"]
        assert "lector_session=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Path=/" in cookie
        second = c.get("/auth", params={"token": "arranque"}, follow_redirects=False)
        assert second.status_code == 403
        assert second.json() == {"detail": "token inválido"}


def test_wrong_token_is_rejected(config: AppConfig) -> None:
    with anonymous_client(config) as c:
        assert c.get("/auth", params={"token": "otro"}, follow_redirects=False).status_code == 403
        assert c.get("/auth", follow_redirects=False).status_code == 403
        assert c.get("/auth", params={"token": "é"}, follow_redirects=False).status_code == 403
        c.cookies.clear()
        raw = c.get("/api/health", headers={"cookie": "lector_session=é".encode()})
        assert raw.status_code == 401


def test_api_requires_cookie(config: AppConfig) -> None:
    with anonymous_client(config) as c:
        denied = c.get("/api/health")
        assert denied.status_code == 401
        assert denied.json() == {"detail": "no autenticado"}
        c.get("/auth", params={"token": "arranque"}, follow_redirects=False)
        ok = c.get("/api/health")
        assert ok.status_code == 200
        assert ok.json() == {"status": "ok"}
        c.cookies.set("lector_session", "x")
        assert c.get("/api/health").status_code == 401


def test_host_is_checked(client: TestClient) -> None:
    bad = client.get("/api/health", headers={"host": "evil.example:8765"})
    assert bad.status_code == 400
    assert bad.json() == {"detail": "host no permitido"}
    assert client.get("/api/health", headers={"host": "localhost:8765"}).status_code == 200


def test_security_headers(config: AppConfig, client: TestClient) -> None:
    ok = client.get("/api/health")
    assert ok.headers["content-security-policy"] == CSP
    assert ok.headers["referrer-policy"] == "no-referrer"
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert ok.headers["cache-control"] == "no-store"
    with anonymous_client(config) as anonymous:
        denied = anonymous.get("/api/health")
    assert denied.status_code == 401
    assert denied.headers["content-security-policy"] == CSP
    assert denied.headers["referrer-policy"] == "no-referrer"
    assert denied.headers["x-content-type-options"] == "nosniff"


def test_no_sync_endpoints(client: TestClient) -> None:
    for route in client.app.routes:  # type: ignore[attr-defined]
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            assert inspect.iscoroutinefunction(endpoint), route.path
