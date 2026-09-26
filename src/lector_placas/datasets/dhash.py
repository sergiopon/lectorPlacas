"""Hash perceptual dHash de 64 bits para deduplicar imágenes (docs/04-evaluacion.md §5.4)."""

from __future__ import annotations

import cv2

from lector_placas.application.ports import ImageBGR


def dhash(image: ImageBGR) -> int:
    """Calcula el dHash de 64 bits de una imagen BGR.

    Args:
        image: imagen BGR de entrada.

    Returns:
        Entero de 64 bits: cada bit compara dos píxeles contiguos de la imagen reducida
        a 9x8 en escala de grises; el primer píxel de la rejilla aporta el bit de mayor peso.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    """Cuenta los bits distintos entre dos hashes.

    Args:
        a: primer hash.
        b: segundo hash.

    Returns:
        Distancia de Hamming entre `a` y `b`.
    """
    return (a ^ b).bit_count()
