from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lector_placas.application.ports import KeyProvider
from lector_placas.infrastructure.config import AppConfig, load_config
from lector_placas.web.factory import create_app
from lector_placas.web.security import SessionAuth, allowed_hosts_for
from lector_placas.web.session import WebSession
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def config() -> AppConfig:
    return load_config(ROOT / "config" / "lector.yaml")


def make_session(config: AppConfig, keys: KeyProvider) -> WebSession:
    repository = InMemoryPlateRepository()
    crop_store = InMemoryCropStore()
    session = WebSession(
        config,
        keys,
        FakeClock(),
        repository,
        repository.browser(),
        crop_store,
        InMemoryExportStore(),
    )
    make_session.repository = repository  # type: ignore[attr-defined]
    make_session.crop_store = crop_store  # type: ignore[attr-defined]
    return session


@contextmanager
def authenticated_client(config: AppConfig) -> Iterator[TestClient]:
    app = create_app(
        config,
        FakeKeyProvider(),
        SessionAuth("arranque"),
        allowed_hosts_for(8765),
        session_factory=make_session,
    )
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.get("/auth", params={"token": "arranque"}, follow_redirects=False)
        yield c


@pytest.fixture
def client(config: AppConfig) -> Iterator[TestClient]:
    with authenticated_client(config) as c:
        yield c
