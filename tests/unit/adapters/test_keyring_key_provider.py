from __future__ import annotations

import pytest
from keyring.errors import KeyringError

from lector_placas.adapters.security.keyring_key_provider import (
    SERVICE_NAME,
    USERNAME,
    KeyringKeyProvider,
)
from lector_placas.domain.errors import KeyUnavailableError


class DictStore:
    def __init__(self, value: str | None = None, fail: bool = False) -> None:
        self.values: dict[tuple[str, str], str] = {}
        if value is not None:
            self.values[(SERVICE_NAME, USERNAME)] = value
        self.fail = fail
        self.reads = 0

    def get_password(self, service: str, username: str) -> str | None:
        self.reads += 1
        if self.fail:
            raise KeyringError("sin backend")
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


def test_reads_existing_key_and_caches() -> None:
    store = DictStore("ab" * 32)
    provider = KeyringKeyProvider(create_if_missing=False, store=store)
    assert provider.master_key() == bytes.fromhex("ab" * 32)
    provider.master_key()
    assert store.reads == 1


def test_creates_key_when_allowed() -> None:
    store = DictStore()
    key = KeyringKeyProvider(create_if_missing=True, store=store).master_key()
    assert len(key) == 32
    assert store.values[(SERVICE_NAME, USERNAME)] == key.hex()


def test_missing_key_without_creation_raises() -> None:
    with pytest.raises(KeyUnavailableError):
        KeyringKeyProvider(create_if_missing=False, store=DictStore()).master_key()


@pytest.mark.parametrize("value", ["zz" * 32, "ab" * 31, "AB" * 32])
def test_corrupt_key_raises(value: str) -> None:
    with pytest.raises(KeyUnavailableError):
        KeyringKeyProvider(create_if_missing=False, store=DictStore(value)).master_key()


def test_keyring_failure_raises() -> None:
    with pytest.raises(KeyUnavailableError):
        KeyringKeyProvider(create_if_missing=True, store=DictStore(fail=True)).master_key()
