# 021 - Adaptador: almacén de recortes cifrado

## Objetivo
Implementar `EncryptedFileCropStore` (puerto `CropStore`): guarda cada recorte como PNG cifrado con
AES-256-GCM en `data/crops/<ref[0:2]>/<ref>.bin`, con escritura atómica y permisos privados.

## Depende de
005, 007, 008.

## Archivos rectores aplicables
- ADR-005; docs/03-modelo-datos.md §2 (formato y política). reglas-seguridad.md SEG-01, SEG-03, SEG-04, SEG-07, SEG-13.

## Archivos a crear/modificar
- `src/lector_placas/adapters/storage/encrypted_crop_store.py`
- `tests/integration/test_encrypted_crop_store.py`

## Dependencias externas
opencv-python==4.14.0.94, cryptography==50.0.1 (ya instalados).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class CropStore(Protocol):
    def save(self, image: ImageBGR) -> str: ...
    def load(self, crop_ref: str) -> ImageBGR: ...
    def delete(self, crop_ref: str) -> None: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
class KeyProvider(Protocol):
    def master_key(self) -> bytes: ...
# de domain/entities.py
CROP_REF_REGEX: Final[re.Pattern[str]]    # ^[0-9a-f]{32}$
# de infrastructure/crypto.py (spec 008)
class KeyPurpose(StrEnum): SQLCIPHER = ...; CROPS = "lector-placas/crops/v1"
def derive_key(master_key: bytes, purpose: KeyPurpose) -> bytes: ...
def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes: ...
def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes: ...
# de infrastructure/paths.py (spec 007)
def resolve_within(base: Path, candidate: Path) -> Path: ...
def ensure_private_dir(path: Path) -> Path: ...
# de domain/errors.py
class CropStoreError, CropNotFoundError(CropStoreError), EncryptionError
```
```python
# adapters/storage/encrypted_crop_store.py — a implementar
class EncryptedFileCropStore:
    def __init__(self, root: Path, key_provider: KeyProvider) -> None: ...
    def save(self, image: ImageBGR) -> str: ...
    def load(self, crop_ref: str) -> ImageBGR: ...
    def delete(self, crop_ref: str) -> None: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
```

## Comportamiento esperado
1. `__init__`: `self._root = ensure_private_dir(root)`; `self._key = derive_key(key_provider.master_key(), KeyPurpose.CROPS)`.
2. `_path_for(ref)`: valida `CROP_REF_REGEX` (si no → `CropStoreError("referencia de recorte inválida")`);
   devuelve `resolve_within(self._root, Path(ref[:2]) / f"{ref}.bin")`.
3. `save(image)`: la imagen debe ser `uint8`, 3 dimensiones, 3 canales y no vacía (si no → `CropStoreError`).
   `ok, encoded = cv2.imencode(".png", image)`; `not ok` → `CropStoreError`. `ref = secrets.token_hex(16)`;
   `blob = encrypt(self._key, encoded.tobytes(), ref.encode("ascii"))`; `ensure_private_dir(path.parent)`;
   escritura atómica: `tmp = path.with_suffix(".tmp")`, `os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`,
   escribir todo, `os.fsync`, cerrar, `os.replace(tmp, path)`. `OSError` → `CropStoreError("no se pudo guardar el recorte") from e`
   (borrando `tmp` si quedó). Devuelve `ref`.
4. `load(ref)`: ruta; si no existe → `CropNotFoundError("recorte no encontrado")`; `decrypt(self._key, blob, ref.encode("ascii"))`
   (`EncryptionError` se propaga); `cv2.imdecode(np.frombuffer(plain, np.uint8), cv2.IMREAD_COLOR)`; `None` → `CropStoreError`.
5. `delete(ref)`: `path.unlink(missing_ok=True)`; `OSError` → `CropStoreError`.
6. `delete_older_than(cutoff)`: recorre `self._root.glob("*/*.bin")` y `self._root.glob("*/*.tmp")`; borra los de
   `stat().st_mtime < cutoff.timestamp()`; devuelve cuántos borró. `OSError` → `CropStoreError`.
7. Nunca escribe PNG descifrado a disco.

## Casos borde y manejo de errores
- Dos `save` de la misma imagen producen refs y blobs distintos.

## Tests de aceptación
```python
# tests/integration/test_encrypted_crop_store.py
from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.storage.encrypted_crop_store import EncryptedFileCropStore
from lector_placas.domain.errors import CropNotFoundError, CropStoreError, EncryptionError
from tests.fixtures.fakes import FakeKeyProvider

pytestmark = pytest.mark.integration


def image() -> np.ndarray:
    rng = np.random.default_rng(1)
    return rng.integers(0, 255, (30, 100, 3), dtype=np.uint8)


def store(tmp_path: Path, key: bytes = bytes(range(32))) -> EncryptedFileCropStore:
    return EncryptedFileCropStore(tmp_path / "crops", FakeKeyProvider(key))


def test_roundtrip_is_lossless_and_encrypted(tmp_path: Path) -> None:
    crops = store(tmp_path)
    ref = crops.save(image())
    np.testing.assert_array_equal(crops.load(ref), image())
    path = tmp_path / "crops" / ref[:2] / f"{ref}.bin"
    assert b"\x89PNG" not in path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "crops").stat().st_mode) == 0o700
    assert not list((tmp_path / "crops").rglob("*.tmp"))


def test_refs_are_random(tmp_path: Path) -> None:
    crops = store(tmp_path)
    assert crops.save(image()) != crops.save(image())


def test_wrong_key_and_tamper(tmp_path: Path) -> None:
    ref = store(tmp_path).save(image())
    with pytest.raises(EncryptionError):
        store(tmp_path, key=bytes(32)).load(ref)
    path = tmp_path / "crops" / ref[:2] / f"{ref}.bin"
    data = bytearray(path.read_bytes())
    data[20] ^= 1
    path.write_bytes(bytes(data))
    with pytest.raises(EncryptionError):
        store(tmp_path).load(ref)


def test_delete_and_missing(tmp_path: Path) -> None:
    crops = store(tmp_path)
    ref = crops.save(image())
    crops.delete(ref)
    crops.delete(ref)
    with pytest.raises(CropNotFoundError):
        crops.load(ref)
    with pytest.raises(CropStoreError):
        crops.load("../etc/passwd")
    with pytest.raises(CropStoreError):
        crops.save(np.zeros((0, 3, 3), np.uint8))


def test_delete_older_than(tmp_path: Path) -> None:
    crops = store(tmp_path)
    old_ref = crops.save(image())
    new_ref = crops.save(image())
    old_path = tmp_path / "crops" / old_ref[:2] / f"{old_ref}.bin"
    past = (datetime.now(UTC) - timedelta(days=40)).timestamp()
    os.utime(old_path, (past, past))
    assert crops.delete_older_than(datetime.now(UTC) - timedelta(days=30)) == 1
    assert not old_path.exists()
    np.testing.assert_array_equal(crops.load(new_ref), image())
```

## Fuera de alcance
Decidir qué recortes expiran (spec 025).

## Definition of Done
- [ ] `uv run pytest -m integration tests/integration/test_encrypted_crop_store.py` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
