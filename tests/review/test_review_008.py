from __future__ import annotations

import os

import pytest

from lector_placas.domain.errors import EncryptionError
from lector_placas.infrastructure.crypto import NONCE_SIZE, KeyPurpose, decrypt, derive_key, encrypt

KEY = derive_key(bytes(range(32)), KeyPurpose.CROPS)


def test_nonces_are_unique_over_many_encryptions() -> None:
    nonces = {encrypt(KEY, b"x", b"a")[:NONCE_SIZE] for _ in range(1000)}
    assert len(nonces) == 1000


def test_minimum_length_blob() -> None:
    blob = encrypt(KEY, b"", b"a")
    assert len(blob) == 28
    assert decrypt(KEY, blob, b"a") == b""
    with pytest.raises(EncryptionError):
        decrypt(KEY, os.urandom(28), b"a")
    with pytest.raises(EncryptionError):
        decrypt(KEY, blob[:27], b"a")
