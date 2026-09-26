"""Derivación de subclaves (HKDF-SHA256) y cifrado autenticado AES-256-GCM."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from lector_placas.domain.errors import EncryptionError

KEY_SIZE: Final[int] = 32
NONCE_SIZE: Final[int] = 12
TAG_SIZE: Final[int] = 16

_BAD_MASTER_KEY_MESSAGE = "la clave maestra debe tener 32 bytes"
_BAD_KEY_MESSAGE = "la clave debe tener 32 bytes"


class KeyPurpose(StrEnum):
    """Propósito de una subclave derivada de la clave maestra."""

    SQLCIPHER = "lector-placas/sqlcipher/v1"
    CROPS = "lector-placas/crops/v1"


def derive_key(master_key: bytes, purpose: KeyPurpose) -> bytes:
    """Deriva una subclave de 32 bytes a partir de la clave maestra.

    Args:
        master_key: clave maestra de 32 bytes.
        purpose: propósito que separa criptográficamente la subclave.

    Returns:
        Subclave derivada de 32 bytes.

    Raises:
        EncryptionError: si `master_key` no tiene 32 bytes.
    """
    if len(master_key) != KEY_SIZE:
        raise EncryptionError(_BAD_MASTER_KEY_MESSAGE)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=None,
        info=purpose.value.encode("ascii"),
    )
    return hkdf.derive(master_key)


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Cifra `plaintext` con AES-256-GCM y antepone el nonce aleatorio.

    Args:
        key: clave de 32 bytes.
        plaintext: datos en claro (puede estar vacío).
        aad: datos autenticados pero no cifrados.

    Returns:
        `nonce + texto cifrado + etiqueta`, con el nonce de 12 bytes al inicio.

    Raises:
        EncryptionError: si `key` no tiene 32 bytes.
    """
    if len(key) != KEY_SIZE:
        raise EncryptionError(_BAD_KEY_MESSAGE)
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    """Descifra `blob` (nonce + texto cifrado + etiqueta) con AES-256-GCM.

    Args:
        key: clave de 32 bytes.
        blob: datos cifrados producidos por `encrypt`.
        aad: datos autenticados pero no cifrados.

    Returns:
        El texto en claro original.

    Raises:
        EncryptionError: si `key` no tiene 32 bytes, si `blob` está truncado o si la
            verificación de integridad falla.
    """
    if len(key) != KEY_SIZE:
        raise EncryptionError(_BAD_KEY_MESSAGE)
    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise EncryptionError("datos cifrados truncados")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_SIZE], blob[NONCE_SIZE:], aad)
    except InvalidTag as e:
        raise EncryptionError("no se pudo descifrar: clave o datos inválidos") from e
