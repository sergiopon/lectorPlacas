"""Textos en español de estados, tipos de vehículo y formatos de tiempo (GUI, ADR-015)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final

from lector_placas.application.ports import RunStatus
from lector_placas.domain.entities import ReviewStatus, VehicleType

STATUS_LABELS: Final[Mapping[ReviewStatus, str]] = MappingProxyType(
    {
        ReviewStatus.CONFIRMED: "confirmado",
        ReviewStatus.UNVERIFIED: "sin verificar",
        ReviewStatus.REJECTED: "rechazado",
        ReviewStatus.CORRECTED: "corregido",
    }
)

VEHICLE_LABELS: Final[Mapping[VehicleType, str]] = MappingProxyType(
    {
        VehicleType.CAR: "carro",
        VehicleType.MOTORCYCLE: "moto",
        VehicleType.BUS: "bus",
        VehicleType.TRUCK: "camión",
    }
)

RUN_STATUS_LABELS: Final[Mapping[RunStatus, str]] = MappingProxyType(
    {
        RunStatus.COMPLETED: "completada",
        RunStatus.FAILED: "fallida",
        RunStatus.RUNNING: "en curso",
    }
)

_MS_PER_SECOND: Final[int] = 1000
_MS_PER_MINUTE: Final[int] = 60 * _MS_PER_SECOND
_MS_PER_HOUR: Final[int] = 60 * _MS_PER_MINUTE
_PERCENT_FACTOR: Final[int] = 100


def video_time(ms: int) -> str:
    """Formatea una duración o posición de video.

    Args:
        ms: milisegundos, `>= 0`.

    Returns:
        `"mm:ss.mmm"`, o `"h:mm:ss.mmm"` si `ms` alcanza una hora o más.
    """
    hours, rest = divmod(ms, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    seconds, millis = divmod(rest, _MS_PER_SECOND)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def local_datetime(value: datetime) -> str:
    """Convierte `value` a hora local y la formatea.

    Args:
        value: instante con zona horaria.

    Returns:
        El texto `"%Y-%m-%d %H:%M:%S"` en hora local.
    """
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def percent(value: float) -> str:
    """Formatea una fracción como porcentaje entero.

    Args:
        value: fracción en `[0, 1]`.

    Returns:
        El texto `"NN %"`, p. ej. `percent(0.873) == "87 %"`.
    """
    return f"{round(value * _PERCENT_FACTOR)} %"
