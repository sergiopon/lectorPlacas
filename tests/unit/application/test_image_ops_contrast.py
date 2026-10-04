"""Tests de aceptación para `rms_contrast` (spec 059)."""

from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.image_ops import rms_contrast


def test_uniform_image_has_zero_contrast() -> None:
    """Una imagen uniforme tiene contraste 0.0."""
    image = np.full((10, 30, 3), 90, dtype=np.uint8)
    assert rms_contrast(image) == 0.0


def test_half_black_half_white() -> None:
    """Una imagen mitad negra mitad blanca tiene contraste 127.5."""
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    image[:, 10:, :] = 255
    assert rms_contrast(image) == pytest.approx(127.5)


def test_channel_weights() -> None:
    """El contraste usa los pesos CIE correctos."""
    # Dos píxeles con valores BGR extremos
    # Píxel 0: (B=255, G=0, R=0) → luminancia = 0.114 * 255 = 29.07
    # Píxel 1: (B=0, G=0, R=0) → luminancia = 0.0
    # Desviación típica: sqrt(((29.07 - 14.535)^2 + (0 - 14.535)^2) / 2) ≈ 14.535
    image = np.zeros((2, 1, 3), dtype=np.uint8)
    image[0, 0, 0] = 255  # B
    result = rms_contrast(image)
    assert result == pytest.approx(14.535, rel=1e-3)
