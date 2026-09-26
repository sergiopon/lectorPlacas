"""Muestreador de frames por tiempo (ADR-006)."""

from __future__ import annotations

import math
from typing import Final

from lector_placas.domain.errors import ConfigurationError, InvalidEntityError

TOLERANCE_MS: Final[float] = 1.0
_MS_PER_S: Final[float] = 1000.0


class TimeBasedFrameSampler:
    """Decide qué frames procesar según su marca de tiempo y el fps objetivo.

    Implementa la regla de ADR-006: procesa un frame cuando transcurrió al menos
    `1000 / target_fps` menos la tolerancia desde el último frame procesado. Al
    basarse en el timestamp y no en el índice, es correcto con fps variable.
    """

    def __init__(self, target_fps: float) -> None:
        """Inicializa el muestreador con el fps objetivo del perfil.

        Args:
            target_fps: frames por segundo objetivo; debe ser finito y > 0.

        Raises:
            ConfigurationError: si `target_fps` no es finito o es <= 0.
        """
        if not math.isfinite(target_fps) or target_fps <= 0.0:
            raise ConfigurationError("target_fps debe ser > 0")
        self._interval_ms: float = _MS_PER_S / target_fps
        self._last_ms: int | None = None

    def should_process(self, timestamp_ms: int) -> bool:
        """Indica si el frame con esa marca de tiempo debe procesarse.

        Procesa el primer frame, los saltos hacia atrás en el tiempo y los frames
        que distan del último procesado al menos el intervalo menos la tolerancia.

        Args:
            timestamp_ms: marca de tiempo del frame en milisegundos.

        Returns:
            `True` si el frame debe procesarse.

        Raises:
            InvalidEntityError: si `timestamp_ms` es negativo.
        """
        if timestamp_ms < 0:
            raise InvalidEntityError("timestamp_ms debe ser >= 0")
        if (
            self._last_ms is None
            or timestamp_ms < self._last_ms
            or timestamp_ms - self._last_ms >= self._interval_ms - TOLERANCE_MS
        ):
            self._last_ms = timestamp_ms
            return True
        return False

    def reset(self) -> None:
        """Reinicia el estado para que el próximo frame vuelva a procesarse."""
        self._last_ms = None
