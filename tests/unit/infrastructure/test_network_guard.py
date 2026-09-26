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
