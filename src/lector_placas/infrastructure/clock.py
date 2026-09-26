"""Reloj del sistema basado en la hora UTC."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Reloj del sistema que devuelve la hora UTC actual."""

    def now(self) -> datetime:
        """Devuelve la hora UTC actual.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            `datetime` con `tzinfo=UTC`.

        Raises:
            Ninguna.
        """
        return datetime.now(UTC)
