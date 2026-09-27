from __future__ import annotations

import pytest

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.errors import CropStoreError
from lector_placas.gui.session import GuiSession, open_session
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)


class _FakePurge:
    def __init__(self, result: PurgeResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self) -> PurgeResult:
        self.calls += 1
        return self.result


def _patch_composition(monkeypatch, repository, purge) -> None:
    monkeypatch.setattr(composition, "build_repository", lambda config, keys: repository)
    monkeypatch.setattr(composition, "build_crop_store", lambda config, keys: InMemoryCropStore())
    monkeypatch.setattr(composition, "build_export_store", lambda config: InMemoryExportStore())
    monkeypatch.setattr(composition, "build_purge", lambda *args, **kwargs: purge)


def test_open_session_purges_and_returns_result(config: AppConfig, monkeypatch) -> None:
    repository = InMemoryPlateRepository()
    expected = PurgeResult(1, 2, 3, 4, 5)
    purge = _FakePurge(expected)
    _patch_composition(monkeypatch, repository, purge)
    session, result = open_session(config, FakeKeyProvider())
    try:
        assert result is expected
        assert purge.calls == 1
        assert session.browser is repository
    finally:
        session.close()


def test_open_session_closes_repository_on_failure(config: AppConfig, monkeypatch) -> None:
    repository = InMemoryPlateRepository()

    def boom(config: AppConfig, keys) -> InMemoryCropStore:
        raise CropStoreError("recortes no disponibles")

    monkeypatch.setattr(composition, "build_repository", lambda config, keys: repository)
    monkeypatch.setattr(composition, "build_crop_store", boom)
    with pytest.raises(CropStoreError):
        open_session(config, FakeKeyProvider())
    assert repository.closed is True


def test_session_close_is_idempotent(config: AppConfig) -> None:
    repository = InMemoryPlateRepository()
    session = GuiSession(
        config,
        FakeKeyProvider(),
        FakeClock(),
        repository,
        repository,
        InMemoryCropStore(),
        InMemoryExportStore(),
    )
    session.close()
    session.close()
    assert repository.closed is True
