"""Almacén de recortes de placa cifrados con AES-256-GCM en disco."""

from __future__ import annotations

import contextlib
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Final, cast

import cv2
import numpy as np

from lector_placas.application.ports import ImageBGR, KeyProvider
from lector_placas.domain.entities import CROP_REF_REGEX
from lector_placas.domain.errors import CropNotFoundError, CropStoreError
from lector_placas.infrastructure.crypto import KeyPurpose, decrypt, derive_key, encrypt
from lector_placas.infrastructure.paths import ensure_private_dir, resolve_within

_REF_HEX_BYTES: Final[int] = 16
_NDIM: Final[int] = 3
_CHANNELS: Final[int] = 3
_BLOB_GLOB: Final[str] = "*/*.bin"
_TMP_GLOB: Final[str] = "*/*.tmp"

_INVALID_REF_MESSAGE: Final[str] = "referencia de recorte inválida"
_NOT_FOUND_MESSAGE: Final[str] = "recorte no encontrado"
_SAVE_MESSAGE: Final[str] = "no se pudo guardar el recorte"
_LOAD_MESSAGE: Final[str] = "no se pudo leer el recorte"
_DELETE_MESSAGE: Final[str] = "no se pudo borrar el recorte"
_INVALID_IMAGE_MESSAGE: Final[str] = "imagen de recorte inválida"
_ENCODE_MESSAGE: Final[str] = "no se pudo codificar el recorte"
_DECODE_MESSAGE: Final[str] = "no se pudo decodificar el recorte"


class EncryptedFileCropStore:
    """Guarda cada recorte como PNG cifrado en `data/crops/<ref[0:2]>/<ref>.bin`."""

    def __init__(self, root: Path, key_provider: KeyProvider) -> None:
        """Crea el almacén cifrado sobre el directorio indicado.

        Args:
            root: directorio raíz de los recortes; se crea con permisos 0700.
            key_provider: proveedor de la clave maestra de 32 bytes.
        """
        self._root = ensure_private_dir(root)
        self._key = derive_key(key_provider.master_key(), KeyPurpose.CROPS)

    def save(self, image: ImageBGR) -> str:
        """Cifra y guarda un recorte con escritura atómica y permisos 0600.

        Args:
            image: imagen BGR `uint8` no vacía de `(alto, ancho, 3)`.

        Returns:
            `crop_ref` de 32 hex que identifica el recorte guardado.

        Raises:
            CropStoreError: si la imagen no es válida o falla la escritura.
            EncryptionError: si falla el cifrado.
        """
        self._validate(image)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise CropStoreError(_ENCODE_MESSAGE)
        ref = secrets.token_hex(_REF_HEX_BYTES)
        blob = encrypt(self._key, encoded.tobytes(), ref.encode("ascii"))
        path = self._path_for(ref)
        ensure_private_dir(path.parent)
        self._write_atomic(path, blob)
        return ref

    def load(self, crop_ref: str) -> ImageBGR:
        """Descifra y decodifica un recorte.

        Args:
            crop_ref: referencia de 32 hex devuelta por `save`.

        Returns:
            Imagen BGR idéntica píxel a píxel a la guardada.

        Raises:
            CropStoreError: si la referencia es inválida o no se puede decodificar.
            CropNotFoundError: si el recorte no existe en disco.
            EncryptionError: si el descifrado falla por clave o datos alterados.
        """
        path = self._path_for(crop_ref)
        if not path.exists():
            raise CropNotFoundError(_NOT_FOUND_MESSAGE)
        try:
            blob = path.read_bytes()
        except OSError as e:
            raise CropStoreError(_LOAD_MESSAGE) from e
        plain = decrypt(self._key, blob, crop_ref.encode("ascii"))
        image = cv2.imdecode(np.frombuffer(plain, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise CropStoreError(_DECODE_MESSAGE)
        return cast(ImageBGR, image)

    def delete(self, crop_ref: str) -> None:
        """Borra un recorte; no falla si ya no existe.

        Args:
            crop_ref: referencia de 32 hex.

        Raises:
            CropStoreError: si la referencia es inválida o falla el borrado.
        """
        path = self._path_for(crop_ref)
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            raise CropStoreError(_DELETE_MESSAGE) from e

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra los recortes y temporales modificados antes del corte.

        Args:
            cutoff: fecha de corte; se borran los archivos con mtime anterior.

        Returns:
            Número de archivos borrados.

        Raises:
            CropStoreError: si falla el borrado de algún archivo.
        """
        limit = cutoff.timestamp()
        deleted = 0
        for path in [*self._root.glob(_BLOB_GLOB), *self._root.glob(_TMP_GLOB)]:
            try:
                if path.stat().st_mtime < limit:
                    path.unlink()
                    deleted += 1
            except OSError as e:
                raise CropStoreError(_DELETE_MESSAGE) from e
        return deleted

    def _path_for(self, ref: str) -> Path:
        """Valida la referencia y devuelve su ruta resuelta dentro de la raíz."""
        if CROP_REF_REGEX.fullmatch(ref) is None:
            raise CropStoreError(_INVALID_REF_MESSAGE)
        return resolve_within(self._root, Path(ref[:2]) / f"{ref}.bin")

    @staticmethod
    def _validate(image: ImageBGR) -> None:
        """Comprueba que la imagen sea BGR `uint8`, de 3 dimensiones y no vacía."""
        if (
            image.dtype != np.uint8
            or image.ndim != _NDIM
            or image.shape[2] != _CHANNELS
            or image.size == 0
        ):
            raise CropStoreError(_INVALID_IMAGE_MESSAGE)

    @staticmethod
    def _write_atomic(path: Path, blob: bytes) -> None:
        """Escribe `blob` en `path` mediante temporal, `fsync` y `os.replace`."""
        tmp = path.with_suffix(".tmp")
        try:
            descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as e:
            raise CropStoreError(_SAVE_MESSAGE) from e
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(path)
        except OSError as e:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise CropStoreError(_SAVE_MESSAGE) from e
