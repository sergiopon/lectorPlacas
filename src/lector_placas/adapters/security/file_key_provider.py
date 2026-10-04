"""Proveedor de clave maestra desde un archivo (para Docker secrets)."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Final

from lector_placas.adapters.security.keyring_key_provider import HEX_KEY_REGEX, KEY_SIZE
from lector_placas.domain.errors import KeyUnavailableError

KEY_FILE_ENV: Final[str] = "LECTOR_KEY_FILE"


class FileKeyProvider:
    """Provee la clave maestra de 32 bytes desde un archivo privado."""

    def __init__(self, path: Path) -> None:
        """Inicializa el proveedor.

        Args:
            path: ruta del archivo que contiene la clave en hex (32 bytes = 64 caracteres hex).
        """
        self._path = path
        self._key: bytes | None = None

    def master_key(self) -> bytes:
        """Devuelve la clave maestra de 32 bytes desde el archivo (con caché en memoria).

        Returns:
            La clave maestra de 32 bytes.

        Raises:
            KeyUnavailableError: si el archivo no existe, no es legible, está corrupto o
                tiene permisos inadecuados.
        """
        if self._key is not None:
            return self._key

        if not self._path.is_absolute():
            raise KeyUnavailableError("LECTOR_KEY_FILE debe ser una ruta absoluta")

        content = self._read_file()
        if HEX_KEY_REGEX.fullmatch(content) is None:
            raise KeyUnavailableError("el archivo de clave está corrupto")

        self._key = bytes.fromhex(content)
        return self._key

    def _read_file(self) -> str:
        """Lee y valida el archivo de clave.

        Returns:
            Contenido del archivo (hex, sin salto final).

        Raises:
            KeyUnavailableError: si el archivo no es accesible o válido.
        """
        st = self._stat_file()
        self._validate_permissions(st)
        content = self._read_content()
        if content.endswith("\n"):
            content = content[:-1]
        return content

    def _stat_file(self) -> os.stat_result:
        """Obtiene metadatos del archivo.

        Returns:
            Resultado de os.lstat().

        Raises:
            KeyUnavailableError: si el archivo no existe o no es accesible.
        """
        try:
            return os.lstat(self._path)
        except FileNotFoundError as e:
            raise KeyUnavailableError("archivo de clave no encontrado") from e
        except OSError as e:
            raise KeyUnavailableError("archivo de clave no legible") from e

    def _validate_permissions(self, st: os.stat_result) -> None:
        """Valida que el archivo sea un archivo regular con permisos seguros.

        Args:
            st: resultado de os.lstat().

        Raises:
            KeyUnavailableError: si los permisos o tipo no son válidos.
        """
        if not stat.S_ISREG(st.st_mode):
            raise KeyUnavailableError("el archivo de clave debe ser un archivo regular")

        if st.st_uid != os.getuid():
            raise KeyUnavailableError("el archivo de clave pertenece a otro usuario")

        if st.st_mode & 0o077 != 0:
            raise KeyUnavailableError("el archivo de clave tiene permisos demasiado abiertos")

    def _read_content(self) -> str:
        """Lee el contenido del archivo como ASCII.

        Returns:
            Contenido del archivo.

        Raises:
            KeyUnavailableError: si el archivo no es legible.
        """
        try:
            return self._path.read_text(encoding="ascii", newline="")
        except (OSError, UnicodeDecodeError) as e:
            raise KeyUnavailableError("archivo de clave no legible") from e


def write_key_file(path: Path, key: bytes) -> None:
    """Escribe la clave maestra en un archivo con permisos restrictivos.

    Args:
        path: ruta donde crear el archivo.
        key: clave maestra de 32 bytes.

    Raises:
        KeyUnavailableError: si la clave es inválida, el archivo ya existe o
            no se puede escribir.
    """
    if len(key) != KEY_SIZE:
        raise KeyUnavailableError("clave maestra inválida")

    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    except FileExistsError as e:
        raise KeyUnavailableError("el archivo de clave ya existe") from e
    except OSError as e:
        raise KeyUnavailableError("no se pudo escribir el archivo de clave") from e

    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(key.hex() + "\n")
    except OSError as e:
        raise KeyUnavailableError("no se pudo escribir el archivo de clave") from e

    path.chmod(0o400)
