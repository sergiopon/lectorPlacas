# 008 - Infraestructura y adaptador: cifrado y clave maestra

## Objetivo
Implementar la derivación de subclaves (HKDF-SHA256), el cifrado autenticado AES-256-GCM y el
proveedor de clave maestra respaldado por el keyring del sistema operativo.

## Depende de
001, 005.

## Archivos rectores aplicables
- ADR-005 (esquema de claves). reglas-seguridad.md SEG-01, SEG-02, SEG-16, SEG-26.
- ARQUITECTURA.md §6 (errores propios, `raise ... from e`).

## Archivos a crear/modificar
- `src/lector_placas/infrastructure/crypto.py`
- `src/lector_placas/adapters/security/keyring_key_provider.py`
- `tests/unit/infrastructure/test_crypto.py`
- `tests/unit/adapters/__init__.py`
- `tests/unit/adapters/test_keyring_key_provider.py`

## Dependencias externas
cryptography==50.0.1, keyring==25.7.0 (ya instalados).

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
class KeyProvider(Protocol):
    def master_key(self) -> bytes: ...   # 32 bytes; KeyUnavailableError
# de domain/errors.py
class EncryptionError(LectorPlacasError): ...
class KeyUnavailableError(LectorPlacasError): ...
```
```python
# infrastructure/crypto.py — a implementar
KEY_SIZE: Final[int] = 32
NONCE_SIZE: Final[int] = 12
TAG_SIZE: Final[int] = 16

class KeyPurpose(StrEnum):
    SQLCIPHER = "lector-placas/sqlcipher/v1"
    CROPS = "lector-placas/crops/v1"

def derive_key(master_key: bytes, purpose: KeyPurpose) -> bytes: ...
def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes: ...
def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes: ...
```
```python
# adapters/security/keyring_key_provider.py — a implementar
SERVICE_NAME: Final[str] = "lector-placas"
USERNAME: Final[str] = "master-key"

class PasswordStore(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...

class SystemPasswordStore:
    """Delegación directa a keyring.get_password / keyring.set_password."""
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...

class KeyringKeyProvider:
    def __init__(self, create_if_missing: bool, store: PasswordStore | None = None) -> None: ...
    def master_key(self) -> bytes: ...
```

## Comportamiento esperado
1. `derive_key`: `len(master_key) != KEY_SIZE` → `EncryptionError("la clave maestra debe tener 32 bytes")`.
   Devuelve `HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.value.encode("ascii")).derive(master_key)`
   (imports: `from cryptography.hazmat.primitives import hashes`, `from cryptography.hazmat.primitives.kdf.hkdf import HKDF`).
2. `encrypt`: clave de 32 bytes (si no → `EncryptionError`); `nonce = os.urandom(NONCE_SIZE)`;
   devuelve `nonce + AESGCM(key).encrypt(nonce, plaintext, aad)` (`from cryptography.hazmat.primitives.ciphers.aead import AESGCM`).
3. `decrypt`: clave de 32 bytes; `len(blob) < NONCE_SIZE + TAG_SIZE` → `EncryptionError("datos cifrados truncados")`;
   `AESGCM(key).decrypt(blob[:12], blob[12:], aad)`; `cryptography.exceptions.InvalidTag` →
   `EncryptionError("no se pudo descifrar: clave o datos inválidos") from e`.
4. `SystemPasswordStore`: llama `keyring.get_password(service, username)` / `keyring.set_password(...)`.
5. `KeyringKeyProvider.__init__`: `store` por defecto `SystemPasswordStore()`. Guarda `create_if_missing`. Caché interna `_key: bytes | None = None`.
6. `master_key()`:
   - Si `_key` ya está, devolverla.
   - `value = store.get_password(SERVICE_NAME, USERNAME)`; `keyring.errors.KeyringError` → `KeyUnavailableError("keyring no disponible") from e`.
   - `value is None`: si `create_if_missing` → `key = os.urandom(32)`, `store.set_password(SERVICE_NAME, USERNAME, key.hex())` (errores de keyring → `KeyUnavailableError`), cachear y devolver; si no → `KeyUnavailableError("no hay clave maestra; ejecute 'lector key init'")`.
   - `value` no cumple `^[0-9a-f]{64}$` → `KeyUnavailableError("la clave maestra del keyring está corrupta")`.
   - Si no: `bytes.fromhex(value)`, cachear y devolver.
7. Nunca registrar (log) ni incluir la clave en mensajes.

## Casos borde y manejo de errores
- `encrypt` con `plaintext` vacío es válido (devuelve 28 bytes).

## Tests de aceptación
```python
# tests/unit/infrastructure/test_crypto.py
from __future__ import annotations

import pytest

from lector_placas.domain.errors import EncryptionError
from lector_placas.infrastructure.crypto import (
    NONCE_SIZE, TAG_SIZE, KeyPurpose, decrypt, derive_key, encrypt,
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
```
```python
# tests/unit/adapters/test_keyring_key_provider.py
from __future__ import annotations

import pytest
from keyring.errors import KeyringError

from lector_placas.adapters.security.keyring_key_provider import (
    SERVICE_NAME, USERNAME, KeyringKeyProvider,
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
```

## Fuera de alcance
Uso de las claves en BD (spec 020) y recortes (spec 021); comando `lector key init` (spec 028).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `grep -rn "master_key\|\.hex()" src/ | grep -i log` vacío (no se registra la clave).
