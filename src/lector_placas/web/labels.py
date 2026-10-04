"""Textos para el operador de los perfiles de procesamiento."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

PROFILE_TEXT: Final[Mapping[str, tuple[str, str]]] = {
    "parqueadero": ("Parqueadero o entrada", "Vehículos lentos o detenidos, cerca de la cámara"),
    "calle_lenta": ("Calle con tráfico lento", "Tráfico urbano normal"),
    "calle_rapida": ("Vía rápida", "Vehículos a mayor velocidad"),
    "patrulla": ("Patrulla", "Cámara montada en un vehículo en movimiento"),
}


def profile_text(name: str) -> tuple[str, str]:
    """Devuelve (etiqueta, descripción) del perfil `name`."""
    return PROFILE_TEXT.get(name, (name.replace("_", " ").capitalize(), ""))
