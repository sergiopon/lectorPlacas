from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from lector_placas.adapters.security.file_key_provider import (
    FileKeyProvider,
    write_key_file,
)
from lector_placas.domain.errors import KeyUnavailableError


def test_reads_valid_key_file(tmp_path: Path) -> None:
    """Lee un archivo válido con la clave y cachea el resultado."""
    key = bytes(range(32))
    key_file = tmp_path / "key"

    # Escribir archivo con salto final
    key_file.write_text(key.hex() + "\n", encoding="ascii")
    key_file.chmod(0o400)

    provider = FileKeyProvider(key_file)
    assert provider.master_key() == key

    # Sin salto final
    key_file.unlink()
    key_file.write_text(key.hex(), encoding="ascii")
    key_file.chmod(0o600)

    provider = FileKeyProvider(key_file)
    assert provider.master_key() == key

    # Borrar archivo después de una lectura exitosa
    key_file.unlink()

    # La segunda llamada devuelve la clave en caché
    assert provider.master_key() == key


def test_rejects_relative_path() -> None:
    """Rechaza rutas relativas."""
    provider = FileKeyProvider(Path("clave.txt"))
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "LECTOR_KEY_FILE debe ser una ruta absoluta"


def _create_valid_key_file(tmp_path: Path) -> tuple[Path, bytes]:
    """Crea un archivo válido con la clave."""
    key = bytes(range(32))
    valid_file = tmp_path / "valid"
    valid_file.write_text(key.hex() + "\n", encoding="ascii")
    valid_file.chmod(0o400)
    return valid_file, key


def test_rejects_missing_and_symlink(tmp_path: Path) -> None:
    """Rechaza archivos inexistentes, enlaces simbólicos y directorios."""
    # Archivo inexistente
    missing_file = tmp_path / "missing"
    provider = FileKeyProvider(missing_file)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "archivo de clave no encontrado"

    # Enlace simbólico
    valid_file, _ = _create_valid_key_file(tmp_path)
    symlink_file = tmp_path / "symlink"
    symlink_file.symlink_to(valid_file)

    provider = FileKeyProvider(symlink_file)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "el archivo de clave debe ser un archivo regular"

    # Directorio
    dir_path = tmp_path / "dir"
    dir_path.mkdir()
    provider = FileKeyProvider(dir_path)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "el archivo de clave debe ser un archivo regular"


@pytest.mark.parametrize("mode", [0o640, 0o644, 0o444])
def test_rejects_open_permissions(tmp_path: Path, mode: int) -> None:
    """Rechaza archivos con permisos demasiado abiertos."""
    key_file = tmp_path / "key"
    key = bytes(range(32))
    key_file.write_text(key.hex() + "\n", encoding="ascii")
    key_file.chmod(mode)

    provider = FileKeyProvider(key_file)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "el archivo de clave tiene permisos demasiado abiertos"


def test_rejects_other_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rechaza archivos que pertenecen a otro usuario."""
    key_file = tmp_path / "key"
    key = bytes(range(32))
    key_file.write_text(key.hex() + "\n", encoding="ascii")
    key_file.chmod(0o400)

    # Monkeypatch getuid para simular otro usuario
    current_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: current_uid + 1)

    provider = FileKeyProvider(key_file)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "el archivo de clave pertenece a otro usuario"


@pytest.mark.parametrize(
    "content",
    [
        "xyz",
        "ab" * 31 + "c",
        "AB" * 32,
        ("ab" * 32) + "\n\n",
    ],
)
def test_rejects_corrupt(tmp_path: Path, content: str) -> None:
    """Rechaza archivos con contenido corrupto."""
    key_file = tmp_path / "key"
    key_file.write_text(content, encoding="ascii")
    key_file.chmod(0o400)

    provider = FileKeyProvider(key_file)
    with pytest.raises(KeyUnavailableError) as exc_info:
        provider.master_key()
    assert str(exc_info.value) == "el archivo de clave está corrupto"
    assert content not in str(exc_info.value)


def test_write_key_file(tmp_path: Path) -> None:
    """Escribe la clave en un archivo con permisos 0400."""
    key = bytes(range(32))
    key_file = tmp_path / "k"

    write_key_file(key_file, key)

    st = os.lstat(key_file)
    assert stat.S_ISREG(st.st_mode)
    assert (st.st_mode & 0o777) == 0o400

    content = key_file.read_text(encoding="ascii")
    assert content == key.hex() + "\n"

    provider = FileKeyProvider(key_file)
    assert provider.master_key() == key

    with pytest.raises(KeyUnavailableError) as exc_info:
        write_key_file(key_file, key)
    assert str(exc_info.value) == "el archivo de clave ya existe"

    key_file2 = tmp_path / "k2"
    with pytest.raises(KeyUnavailableError) as exc_info:
        write_key_file(key_file2, key[:31])
    assert str(exc_info.value) == "clave maestra inválida"
