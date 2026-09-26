# 019 - Infraestructura: manifiesto de modelos, descarga verificada y guardia de red

## Objetivo
Implementar el registro de modelos verificado por SHA-256, el comando de descarga (única operación con
red) y la guardia que bloquea la red en runtime; crear `config/models.yaml`.

## Depende de
001, 005, 007.

## Archivos rectores aplicables
- ADR-012 (manifiesto, hashes fijados, guardia). reglas-seguridad.md SEG-17, SEG-19, SEG-20, SEG-21.
- docs/03-modelo-datos.md §5 (formato y validaciones del manifiesto).

## Archivos a crear/modificar
- `config/models.yaml` (contenido literal de docs/03-modelo-datos.md §5)
- `src/lector_placas/infrastructure/model_registry.py`
- `src/lector_placas/infrastructure/model_fetcher.py`
- `src/lector_placas/infrastructure/network_guard.py`
- `tests/unit/infrastructure/test_model_registry.py`
- `tests/unit/infrastructure/test_model_fetcher.py`
- `tests/unit/infrastructure/test_network_guard.py`

## Dependencias externas
pydantic==2.13.5, PyYAML==6.0.3 (ya instalados). stdlib `urllib.request`, `socket`, `hashlib`.

## Interfaces y tipos involucrados
```python
# de application/ports.py
class ModelRegistry(Protocol):
    def verified_path(self, model_id: str) -> Path: ...
# de infrastructure/input_validation.py (spec 007)
def sha256_file(path: Path) -> str: ...
# de infrastructure/paths.py (spec 007)
def resolve_within(base: Path, candidate: Path) -> Path: ...
def ensure_private_dir(path: Path) -> Path: ...
# de domain/errors.py
class ModelIntegrityError, ModelFetchError, NetworkAccessError, ConfigurationError, InputValidationError
```
```python
# infrastructure/model_registry.py — a implementar
PENDING_EXPORT: Final[str] = "PENDIENTE_EXPORT"

class ModelEntry(BaseModel):          # extra="forbid", frozen=True
    model_id: str                     # ^[a-z0-9][a-z0-9-]{1,63}$
    filename: str                     # sin "/", sin "\\", sin "..", no vacío
    url: str | None                   # None o empieza por "https://github.com/"
    sha256: str                       # ^[0-9a-f]{64}$ o PENDING_EXPORT
    size_bytes: int                   # >= 0
    license: str
    source: str

class ModelManifest(BaseModel):       # extra="forbid", frozen=True
    version: Literal[1]
    models: tuple[ModelEntry, ...]    # model_id únicos, al menos 1
    def entry(self, model_id: str) -> ModelEntry: ...

def load_manifest(path: Path) -> ModelManifest: ...

class ManifestModelRegistry:
    def __init__(self, manifest_path: Path, models_dir: Path) -> None: ...
    def verified_path(self, model_id: str) -> Path: ...

# infrastructure/model_fetcher.py — a implementar
class UrlOpener(Protocol):
    def __call__(self, url: str, timeout: float) -> BinaryIO: ...

ALLOWED_PREFIX: Final[str] = "https://github.com/"
def fetch_models(manifest_path: Path, models_dir: Path, opener: UrlOpener) -> list[str]: ...
def default_opener(url: str, timeout: float) -> BinaryIO: ...   # urllib.request.urlopen(url, timeout=timeout)

# infrastructure/network_guard.py — a implementar
def block_network() -> None: ...
def is_network_blocked() -> bool: ...
```

## Comportamiento esperado
1. `load_manifest(path)`: `yaml.safe_load`; errores de lectura/YAML/validación → `ConfigurationError("manifiesto de modelos inválido: <detalle>")`.
2. `ModelManifest.entry(model_id)`: inexistente → `ModelIntegrityError("modelo desconocido: <id>")`.
3. `ManifestModelRegistry.__init__` carga el manifiesto. `verified_path(model_id)`:
   - `entry.sha256 == PENDING_EXPORT` → `ModelIntegrityError("modelo no exportado: <id>")`.
   - `path = resolve_within(models_dir, Path(model_id) / filename)`; si no existe → `ModelIntegrityError("modelo no encontrado: <id>; ejecute 'lector models fetch'")`.
   - `sha256_file(path) != entry.sha256` → `ModelIntegrityError("hash SHA-256 no coincide: <id>")`.
   - Devuelve `path` (se recalcula el hash en cada llamada).
4. `fetch_models(manifest_path, models_dir, opener)`: para cada entrada con `url` no nulo (en orden):
   - Si el archivo destino ya existe con el hash correcto → se omite.
   - `url` no empieza por `ALLOWED_PREFIX` → `ModelFetchError`.
   - `ensure_private_dir(models_dir / model_id)`; descarga con `opener(url, 60.0)` en bloques de 1 MiB a
     `<destino>.part`, calculando SHA-256 y tamaño; si tamaño ≠ `size_bytes` o hash ≠ `sha256` → borra el
     `.part` y `ModelFetchError("verificación fallida: <id>")`; si no `os.replace(part, destino)`.
   - `OSError`/`urllib.error.URLError` → `ModelFetchError("descarga fallida: <id>") from e`.
   - Devuelve la lista de `model_id` descargados (no los omitidos).
5. `block_network()`: idempotente. Reemplaza `socket.socket.connect`, `socket.socket.connect_ex` y
   `socket.create_connection` por funciones que lanzan `NetworkAccessError("acceso a red bloqueado en runtime")`.
   `is_network_blocked()` indica si ya se aplicó. (Estado de módulo permitido solo aquí, documentado en el docstring.)

## Casos borde y manejo de errores
- `filename` con `..` o `/` se rechaza al validar el manifiesto.
- Mensajes sin rutas absolutas.

## Tests de aceptación
```python
# tests/unit/infrastructure/test_model_registry.py
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from lector_placas.domain.errors import ConfigurationError, ModelIntegrityError
from lector_placas.infrastructure.model_registry import ManifestModelRegistry, load_manifest

ROOT = Path(__file__).resolve().parents[3]
CONTENT = b"modelo sintetico"


def write_manifest(tmp_path: Path, **overrides: object) -> Path:
    entry = {"model_id": "m-uno", "filename": "m.onnx", "url": None,
             "sha256": hashlib.sha256(CONTENT).hexdigest(), "size_bytes": len(CONTENT),
             "license": "MIT", "source": "test"}
    entry.update(overrides)
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [entry]}), encoding="utf-8")
    return path


def test_real_manifest_is_valid() -> None:
    manifest = load_manifest(ROOT / "config" / "models.yaml")
    assert manifest.entry("fpo-cct-xs-v2-global").sha256.startswith("8031afb5")
    assert manifest.entry("yolo26n-coco").sha256 == "PENDIENTE_EXPORT"


def test_verified_path_ok_and_tampered(tmp_path: Path) -> None:
    models = tmp_path / "models"
    (models / "m-uno").mkdir(parents=True)
    target = models / "m-uno" / "m.onnx"
    target.write_bytes(CONTENT)
    registry = ManifestModelRegistry(write_manifest(tmp_path), models)
    assert registry.verified_path("m-uno") == target.resolve()
    target.write_bytes(b"alterado")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("m-uno")


def test_missing_unknown_and_pending(tmp_path: Path) -> None:
    registry = ManifestModelRegistry(write_manifest(tmp_path), tmp_path / "models")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("m-uno")
    with pytest.raises(ModelIntegrityError):
        registry.verified_path("otro")
    pending = ManifestModelRegistry(write_manifest(tmp_path, sha256="PENDIENTE_EXPORT"), tmp_path)
    with pytest.raises(ModelIntegrityError):
        pending.verified_path("m-uno")


@pytest.mark.parametrize("overrides", [
    {"filename": "../x.onnx"}, {"filename": "a/b.onnx"}, {"url": "http://example.com/m"},
    {"sha256": "abc"}, {"model_id": "Mayus"}, {"size_bytes": -1},
])
def test_invalid_manifest(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        load_manifest(write_manifest(tmp_path, **overrides))
```
```python
# tests/unit/infrastructure/test_model_fetcher.py
from __future__ import annotations

import hashlib
import io
import stat
from pathlib import Path
from typing import BinaryIO

import pytest
import yaml

from lector_placas.domain.errors import ModelFetchError
from lector_placas.infrastructure.model_fetcher import fetch_models

CONTENT = b"pesos sinteticos" * 1000
URL = "https://github.com/example/releases/download/v1/m.onnx"


def manifest(tmp_path: Path, content: bytes = CONTENT, url: str = URL) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [{
        "model_id": "m-uno", "filename": "m.onnx", "url": url,
        "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content),
        "license": "MIT", "source": "test"}]}), encoding="utf-8")
    return path


class Opener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> BinaryIO:
        self.calls.append(url)
        return io.BytesIO(self.payload)


def test_downloads_verifies_and_skips_existing(tmp_path: Path) -> None:
    opener = Opener(CONTENT)
    models = tmp_path / "models"
    assert fetch_models(manifest(tmp_path), models, opener) == ["m-uno"]
    assert (models / "m-uno" / "m.onnx").read_bytes() == CONTENT
    assert stat.S_IMODE((models / "m-uno").stat().st_mode) == 0o700
    assert fetch_models(manifest(tmp_path), models, opener) == []
    assert opener.calls == [URL]


def test_hash_mismatch_leaves_nothing(tmp_path: Path) -> None:
    models = tmp_path / "models"
    with pytest.raises(ModelFetchError):
        fetch_models(manifest(tmp_path), models, Opener(b"otra cosa"))
    assert not list((models / "m-uno").glob("*"))


def test_pending_or_null_url_entries_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [{
        "model_id": "local", "filename": "x.onnx", "url": None, "sha256": "PENDIENTE_EXPORT",
        "size_bytes": 0, "license": "AGPL-3.0", "source": "local"}]}), encoding="utf-8")
    assert fetch_models(path, tmp_path / "models", Opener(b"")) == []
```
```python
# tests/unit/infrastructure/test_network_guard.py
from __future__ import annotations

import socket

import pytest

from lector_placas.domain.errors import NetworkAccessError
from lector_placas.infrastructure import network_guard


def test_block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", socket.socket.connect)
    monkeypatch.setattr(socket.socket, "connect_ex", socket.socket.connect_ex)
    monkeypatch.setattr(socket, "create_connection", socket.create_connection)
    monkeypatch.setattr(network_guard, "_BLOCKED", False, raising=False)
    network_guard.block_network()
    network_guard.block_network()
    assert network_guard.is_network_blocked()
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("127.0.0.1", 9))
    with socket.socket() as sock, pytest.raises(NetworkAccessError):
        sock.connect(("127.0.0.1", 9))
```
Nota normativa: el estado de la guardia se guarda en la variable de módulo `_BLOCKED: bool` (el test la reinicia con `monkeypatch`).

## Fuera de alcance
Registro del modelo exportado localmente (lo hace el operador con la salida de spec 030).

## Definition of Done
- [ ] `config/models.yaml` idéntico a docs/03-modelo-datos.md §5.
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `grep -rn "urllib\|socket\|requests" src/ | grep -v "model_fetcher.py\|network_guard.py"` vacío.
