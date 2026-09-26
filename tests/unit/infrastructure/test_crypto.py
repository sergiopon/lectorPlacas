from __future__ import annotations

import pytest

from lector_placas.domain.errors import EncryptionError
from lector_placas.infrastructure.crypto import (
    NONCE_SIZE,
    TAG_SIZE,
    KeyPurpose,
    decrypt,
    derive_key,
    encrypt,
)

MASTER = bytes(range(32))


def test_derive_key_is_deterministic_and_purpose_bound() -> None:
    a = derive_key(MASTER, KeyPurpose.CROPS)
    assert a == derive_key(MASTER, KeyPurpose.CROPS)
    assert a != derive_key(MASTER, KeyPurpose.SQLCIPHER)
    assert len(a) == 32


def test_derive_key_rejects_bad_master() -> None:
    with pytest.raises(EncryptionError):
        derive_key(b"short", KeyPurpose.CROPS)


def test_roundtrip_and_layout() -> None:
    key = derive_key(MASTER, KeyPurpose.CROPS)
    blob = encrypt(key, b"datos sinteticos", b"ref")
    assert len(blob) == NONCE_SIZE + len(b"datos sinteticos") + TAG_SIZE
    assert decrypt(key, blob, b"ref") == b"datos sinteticos"
    assert encrypt(key, b"datos sinteticos", b"ref") != blob


def test_empty_plaintext() -> None:
    key = derive_key(MASTER, KeyPurpose.CROPS)
    assert decrypt(key, encrypt(key, b"", b"a"), b"a") == b""


@pytest.mark.parametrize("case", ["tamper", "aad", "key", "short"])
def test_decrypt_failures(case: str) -> None:
    key = derive_key(MASTER, KeyPurpose.CROPS)
    blob = encrypt(key, b"secreto", b"ref")
    if case == "tamper":
        blob = blob[:-1] + bytes([blob[-1] ^ 1])
    aad = b"otra" if case == "aad" else b"ref"
    other_key = derive_key(MASTER, KeyPurpose.SQLCIPHER) if case == "key" else key
    if case == "short":
        blob = blob[:10]
    with pytest.raises(EncryptionError):
        decrypt(other_key, blob, aad)


def test_encrypt_rejects_bad_key() -> None:
    with pytest.raises(EncryptionError):
        encrypt(b"x" * 16, b"a", b"b")
