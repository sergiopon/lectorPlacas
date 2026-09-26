# 007 - Infraestructura: rutas seguras y validación del video de entrada

## Objetivo
Implementar la resolución segura de rutas (anti path traversal), la creación de directorios privados,
la validación del archivo de video de entrada y el hash SHA-256 de archivos.

## Depende de
001.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-04 (0700), SEG-12 (validación del video), SEG-13 (rutas de salida), SEG-26 (mensajes).
- ARQUITECTURA.md §6.

## Archivos a crear/modificar
- `src/lector_placas/infrastructure/paths.py`
- `src/lector_placas/infrastructure/input_validation.py`
- `tests/unit/infrastructure/test_paths.py`
- `tests/unit/infrastructure/test_input_validation.py`

## Dependencias externas
Ninguna (stdlib).

## Interfaces y tipos involucrados
```python
# de domain/errors.py
class InputValidationError(LectorPlacasError): ...
class UnsafePathError(InputValidationError): ...
```
```python
# infrastructure/paths.py — a implementar
def resolve_within(base: Path, candidate: Path) -> Path: ...
def ensure_private_dir(path: Path) -> Path: ...

# infrastructure/input_validation.py — a implementar
CHUNK_SIZE: Final[int] = 1024 * 1024
def validate_video_path(path: Path, allowed_dirs: Sequence[Path], allowed_extensions: frozenset[str],
                        max_size_bytes: int) -> Path: ...
def sha256_file(path: Path) -> str: ...
```

## Comportamiento esperado
1. `resolve_within(base, candidate)`: `base_r = base.resolve()`; `target = candidate if candidate.is_absolute() else base_r / candidate`;
   `target_r = target.resolve()`; si `not target_r.is_relative_to(base_r)` → `UnsafePathError("ruta fuera del directorio permitido: <candidate.name>")`. Devuelve `target_r`.
2. `ensure_private_dir(path)`: si `path.is_symlink()` o (`path.exists()` y no es directorio) → `UnsafePathError`.
   `path.mkdir(mode=0o700, parents=True, exist_ok=True)`; `os.chmod(path, 0o700)`; devuelve `path`.
   `OSError` → `UnsafePathError("no se pudo preparar el directorio: <path.name>") from e`.
3. `validate_video_path(path, allowed_dirs, allowed_extensions, max_size_bytes)`, en este orden:
   1. `path.is_symlink()` → `InputValidationError("el video no puede ser un enlace simbólico")`.
   2. `resolved = path.resolve(strict=True)`; `FileNotFoundError`/`OSError` → `InputValidationError("el video no existe: <path.name>")`.
   3. `not resolved.is_file()` → `InputValidationError("el video no es un archivo regular")`.
   4. `resolved.suffix.lower() not in allowed_extensions` → `InputValidationError("extensión no permitida: <suffix>")`.
   5. Si `resolved` no está dentro de ningún `d.resolve()` de `allowed_dirs` → `UnsafePathError("el video está fuera de los directorios permitidos")`.
   6. `size = resolved.stat().st_size`; `size == 0` → `InputValidationError("el video está vacío")`;
      `size > max_size_bytes` → `InputValidationError("el video supera el tamaño máximo")`.
   7. Devuelve `resolved`.
4. `sha256_file(path)`: lee en bloques de `CHUNK_SIZE` con `hashlib.sha256`; devuelve `hexdigest()` (minúsculas).
   `OSError` → `InputValidationError("no se pudo leer el archivo: <path.name>") from e`.

## Casos borde y manejo de errores
- Los mensajes solo incluyen el nombre de archivo, nunca la ruta absoluta.
- La decodificabilidad del video la verifica `VideoSourceFactory.open` (spec 010), no este módulo.

## Tests de aceptación
```python
# tests/unit/infrastructure/test_paths.py
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from lector_placas.domain.errors import UnsafePathError
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within


def test_resolve_within_accepts_inside(tmp_path: Path) -> None:
    assert resolve_within(tmp_path, Path("a/b.txt")) == (tmp_path / "a" / "b.txt").resolve()


@pytest.mark.parametrize("candidate", [Path("../x"), Path("a/../../x"), Path("/etc/passwd")])
def test_resolve_within_rejects_escape(tmp_path: Path, candidate: Path) -> None:
    with pytest.raises(UnsafePathError):
        resolve_within(tmp_path / "base", candidate)


def test_resolve_within_rejects_symlink_escape(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_within(base, Path("link/secret"))


def test_ensure_private_dir_creates_0700(tmp_path: Path) -> None:
    target = ensure_private_dir(tmp_path / "data" / "crops")
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_ensure_private_dir_rejects_file_and_symlink(tmp_path: Path) -> None:
    file_path = tmp_path / "f"
    file_path.write_text("x")
    with pytest.raises(UnsafePathError):
        ensure_private_dir(file_path)
    link = tmp_path / "l"
    link.symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        ensure_private_dir(link)
```
```python
# tests/unit/infrastructure/test_input_validation.py
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lector_placas.domain.errors import InputValidationError, UnsafePathError
from lector_placas.infrastructure.input_validation import sha256_file, validate_video_path

EXTS = frozenset({".mp4", ".mov"})


@pytest.fixture
def videos(tmp_path: Path) -> Path:
    directory = tmp_path / "videos"
    directory.mkdir()
    return directory


def make_file(path: Path, size: int = 10) -> Path:
    path.write_bytes(b"\x00" * size)
    return path


def test_valid_video_path(videos: Path) -> None:
    video = make_file(videos / "clip.MP4")
    assert validate_video_path(video, [videos], EXTS, 100) == video.resolve()


def test_rejects_missing_extension_size_and_location(tmp_path: Path, videos: Path) -> None:
    with pytest.raises(InputValidationError):
        validate_video_path(videos / "nada.mp4", [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "a.txt"), [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "big.mp4", 101), [videos], EXTS, 100)
    with pytest.raises(InputValidationError):
        validate_video_path(make_file(videos / "empty.mp4", 0), [videos], EXTS, 100)
    with pytest.raises(UnsafePathError):
        validate_video_path(make_file(tmp_path / "out.mp4"), [videos], EXTS, 100)


def test_rejects_symlink_and_directory(tmp_path: Path, videos: Path) -> None:
    target = make_file(tmp_path / "real.mp4")
    link = videos / "link.mp4"
    link.symlink_to(target)
    with pytest.raises(InputValidationError):
        validate_video_path(link, [videos], EXTS, 100)
    folder = videos / "folder.mp4"
    folder.mkdir()
    with pytest.raises(InputValidationError):
        validate_video_path(folder, [videos], EXTS, 100)


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"lector" * 400_000)
    assert sha256_file(path) == hashlib.sha256(b"lector" * 400_000).hexdigest()
    with pytest.raises(InputValidationError):
        sha256_file(tmp_path / "missing.bin")
```

## Fuera de alcance
Apertura del video con PyAV (spec 010).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
