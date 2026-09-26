"""Guardia que bloquea las conexiones de red durante el runtime (ADR-012, SEG-20).

Estado de módulo: `_BLOCKED` recuerda si la guardia ya se aplicó. Es el único estado
mutable global del paquete y existe porque el bloqueo debe ser un efecto único y
verificable sobre `socket`, compartido por todos los llamadores del proceso.
"""

from __future__ import annotations

import socket
from typing import Final

from lector_placas.domain.errors import NetworkAccessError

BLOCKED_MESSAGE: Final[str] = "acceso a red bloqueado en runtime"

_BLOCKED: bool = False


def _blocked_connect(sock: object, address: object) -> None:
    """Sustituto de `socket.socket.connect` que siempre falla (SEG-20)."""
    raise NetworkAccessError(BLOCKED_MESSAGE)


def _blocked_connect_ex(sock: object, address: object) -> int:
    """Sustituto de `socket.socket.connect_ex` que siempre falla (SEG-20)."""
    raise NetworkAccessError(BLOCKED_MESSAGE)


def _blocked_create_connection(
    address: object,
    timeout: float | None = None,
    source_address: object = None,
    *,
    all_errors: bool = False,
) -> socket.socket:
    """Sustituto de `socket.create_connection` que siempre falla (SEG-20)."""
    raise NetworkAccessError(BLOCKED_MESSAGE)


def block_network() -> None:
    """Bloquea la red del proceso reemplazando la API de conexión de `socket`.

    Idempotente: las llamadas posteriores no cambian nada.

    Raises:
        NetworkAccessError: Desde este momento, cualquier intento de conexión.
    """
    global _BLOCKED  # noqa: PLW0603 - estado único y documentado de la guardia (SEG-20)
    if _BLOCKED:
        return
    socket.socket.connect = _blocked_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked_connect_ex  # type: ignore[method-assign]
    socket.create_connection = _blocked_create_connection
    _BLOCKED = True


def is_network_blocked() -> bool:
    """Indica si `block_network` ya se aplicó en este proceso."""
    return _BLOCKED
