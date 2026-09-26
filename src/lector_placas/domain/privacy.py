"""Enmascarado de textos de placa para logs, mensajes y auditoría (SEG-05)."""

from __future__ import annotations

from typing import Final

MIN_VISIBLE_LENGTH: Final[int] = 2


def mask_plate(text: str) -> str:
    """Devuelve el texto con todo enmascarado salvo el primer y el último carácter.

    Args:
        text: Texto de placa en claro.

    Returns:
        El texto original si tiene longitud menor o igual que 2 (todo enmascarado), o su
        primer carácter, asteriscos y su último carácter.
    """
    if len(text) <= MIN_VISIBLE_LENGTH:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - MIN_VISIBLE_LENGTH) + text[-1]
