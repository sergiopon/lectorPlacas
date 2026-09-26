"""Proveedor de clave maestra respaldado por el keyring del sistema operativo."""

from __future__ import annotations

import os
import re
from typing import Final, Protocol

import keyring
from keyring.errors import KeyringError

from lector_placas.domain.errors import KeyUnavailableError

SERVICE_NAME: Final[str] = "lector-placas"
USERNAME: Final[str] = "master-key"

KEY_SIZE = 32
HEX_KEY_REGEX = re.compile(r"^[0-9a-f]{64}$")


class PasswordStore(Protocol):
    """Almacén de contraseñas (subconjunto de la API de `keyring`)."""

    def get_password(self, service: str, username: str) -> str | None:
        """Devuelve la contraseña almacenada o `None` si no existe."""
        ...

    def set_password(self, service: str, username: str, password: str) -> None:
        """Almacena `password` para `service`/`username`."""
        ...


class SystemPasswordStore:
    """Delegación directa a `keyring.get_password` / `keyring.set_password`."""

    def get_password(self, service: str, username: str) -> str | None:
        """Devuelve la contraseña almacenada en el keyring del sistema.

        Args:
            service: nombre del servicio.
            username: nombre del usuario.

        Returns:
            La contraseña almacenada, o `None` si no existe.
        """
        return keyring.get_password(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        """Almacena `password` en el keyring del sistema.

        Args:
            service: nombre del servicio.
            username: nombre del usuario.
            password: valor a almacenar.
        """
        keyring.set_password(service, username, password)


class KeyringKeyProvider:
    """Provee la clave maestra de 32 bytes almacenada en el keyring."""

    def __init__(self, create_if_missing: bool, store: PasswordStore | None = None) -> None:
        """Inicializa el proveedor.

        Args:
            create_if_missing: si es `True`, genera y almacena la clave cuando no existe.
            store: almacén de contraseñas; por defecto `SystemPasswordStore()`.
        """
        self._create_if_missing = create_if_missing
        self._store = SystemPasswordStore() if store is None else store
        self._key: bytes | None = None

    def master_key(self) -> bytes:
        """Devuelve la clave maestra de 32 bytes (con caché en memoria).

        Returns:
            La clave maestra de 32 bytes.

        Raises:
            KeyUnavailableError: si el keyring no está disponible, si no hay clave y no
                se permite crearla, o si el valor almacenado está corrupto.
        """
        if self._key is not None:
            return self._key
        value = self._read_password()
        if value is None:
            if not self._create_if_missing:
                raise KeyUnavailableError("no hay clave maestra; ejecute 'lector key init'")
            return self._create_key()
        if HEX_KEY_REGEX.fullmatch(value) is None:
            raise KeyUnavailableError("la clave maestra del keyring está corrupta")
        self._key = bytes.fromhex(value)
        return self._key

    def _read_password(self) -> str | None:
        try:
            return self._store.get_password(SERVICE_NAME, USERNAME)
        except KeyringError as e:
            raise KeyUnavailableError("keyring no disponible") from e

    def _create_key(self) -> bytes:
        key = os.urandom(KEY_SIZE)
        try:
            self._store.set_password(SERVICE_NAME, USERNAME, key.hex())
        except KeyringError as e:
            raise KeyUnavailableError("keyring no disponible") from e
        self._key = key
        return key
