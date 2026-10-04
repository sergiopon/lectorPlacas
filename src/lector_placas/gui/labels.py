"""Textos en español de estados, tipos de vehículo y formatos de tiempo (GUI, ADR-015)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final

from lector_placas.application.ports import RunStatus
from lector_placas.domain.entities import ReviewStatus, UnverifiedReason, VehicleType

STATUS_LABELS: Final[Mapping[ReviewStatus, str]] = MappingProxyType(
    {
        ReviewStatus.CONFIRMED: "confirmado",
        ReviewStatus.UNVERIFIED: "sin verificar",
        ReviewStatus.REJECTED: "rechazado",
        ReviewStatus.CORRECTED: "corregido",
        ReviewStatus.ILLEGIBLE: "borrosa",
    }
)

STATUS_BADGES: Final[Mapping[ReviewStatus, str]] = MappingProxyType(
    {
        ReviewStatus.UNVERIFIED: "Por revisar",
        ReviewStatus.CONFIRMED: "Confirmada",
        ReviewStatus.CORRECTED: "Corregida",
        ReviewStatus.REJECTED: "Descartada",
        ReviewStatus.ILLEGIBLE: "Borrosa",
    }
)

REASON_TEXTS: Final[Mapping[UnverifiedReason, str]] = MappingProxyType(
    {
        UnverifiedReason.INSUFFICIENT_READINGS: "Se leyó pocas veces",
        UnverifiedReason.LOW_CONFIDENCE: "El lector no estaba seguro",
        UnverifiedReason.LOW_AGREEMENT: "Las lecturas no coinciden entre sí",
        UnverifiedReason.UNRECOGNIZED_FORMAT: "No parece una placa colombiana",
        UnverifiedReason.UNVERIFIED_FORMAT: "Formato de placa poco común",
        UnverifiedReason.VEHICLE_FORMAT_MISMATCH: "El formato no corresponde al tipo de vehículo",
        UnverifiedReason.AMBIGUOUS_FORMAT: "Encaja en más de un formato",
        UnverifiedReason.CORRECTION_CONFLICT: "Podría ser otra placa: una letra o un número dudoso",
        UnverifiedReason.PREDICTED_ILLEGIBLE: "Parece borrosa (filtro automático)",
        UnverifiedReason.PREDICTED_NOT_PLATE: "Parece que no es una placa (filtro automático)",
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

PROFILE_LABELS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "parqueadero": (
            "Parqueadero o entrada",
            "Vehículos lentos o detenidos, cerca de la cámara",
        ),
        "calle_lenta": ("Calle con tráfico lento", "Tráfico urbano normal"),
        "calle_rapida": ("Vía rápida", "Vehículos a mayor velocidad"),
    }
)

_MS_PER_SECOND: Final[int] = 1000
_MS_PER_MINUTE: Final[int] = 60 * _MS_PER_SECOND
_MS_PER_HOUR: Final[int] = 60 * _MS_PER_MINUTE
_PERCENT_FACTOR: Final[int] = 100
_PLATE_GROUP_SIZE: Final[int] = 6
_PLATE_GROUP_SPLIT: Final[int] = 3


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


def short_time(ms: int) -> str:
    """Formatea una posición de video de forma breve para una tarjeta.

    Args:
        ms: milisegundos, `>= 0`.

    Returns:
        `"m:ss"` (p. ej. `"1:23"`), o `"h:mm:ss"` si `ms` alcanza una hora o más.
    """
    hours, rest = divmod(ms, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    seconds, _ = divmod(rest, _MS_PER_SECOND)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def profile_label(profile: str) -> str:
    """Devuelve el nombre legible de un perfil de escenario.

    Args:
        profile: clave de perfil (p. ej. `"calle_lenta"`).

    Returns:
        El nombre del catálogo o, si el perfil es desconocido, la clave con espacios
        y la primera letra en mayúscula.
    """
    known = PROFILE_LABELS.get(profile)
    if known is not None:
        return known[0]
    return profile.replace("_", " ").capitalize()


def format_plate(text: str) -> str:
    """Separa en dos grupos el texto de una placa de seis caracteres.

    Args:
        text: texto de placa.

    Returns:
        El texto con un espacio tras el tercer carácter si mide seis, o `text` sin cambios.
    """
    if len(text) == _PLATE_GROUP_SIZE:
        return f"{text[:_PLATE_GROUP_SPLIT]} {text[_PLATE_GROUP_SPLIT:]}"
    return text
