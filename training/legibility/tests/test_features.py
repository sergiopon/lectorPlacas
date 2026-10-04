from __future__ import annotations

import pytest

from legibility_training.dataset import Row
from legibility_training.features import feature_vector


def test_feature_vector_reference() -> None:
    """Prueba de referencia del vector de características."""
    row = Row(
        label="legible",
        human_reviewed=True,
        video_group=1,
        vehicle_type="car",
        confidence=0.8,
        agreement=0.75,
        num_readings=4,
        reasons=("low_confidence",),
        plate_width_px=60,
        plate_height_px=20,
        sharpness=99.0,
        contrast=64.0,
        frame_width=1920,
        frame_height=1080,
    )

    result = feature_vector(row)

    expected = [
        0.8,
        0.75,
        1.3862943611198906,
        0.03125,
        0.3333333333333333,
        4.605170185988092,
        0.5,
        0.0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    ]

    for i, (r, e) in enumerate(zip(result, expected, strict=True)):
        assert r == pytest.approx(e), f"Índice {i}: {r} != {e}"


def test_unknown_reasons_ignored_and_motorcycle() -> None:
    """Prueba que razones desconocidas se ignoran y motorcycles se detectan."""
    row = Row(
        label="legible",
        human_reviewed=True,
        video_group=1,
        vehicle_type="motorcycle",
        confidence=0.8,
        agreement=0.75,
        num_readings=4,
        reasons=("predicted_illegible", "correction_conflict"),
        plate_width_px=60,
        plate_height_px=20,
        sharpness=99.0,
        contrast=64.0,
        frame_width=1920,
        frame_height=1080,
    )

    result = feature_vector(row)

    # Posición 8 (numeración desde 1) = índice 7: is_motorcycle → debe ser 1.0
    assert result[7] == 1.0

    # Última posición es reason_correction_conflict → debe ser 1.0
    assert result[-1] == 1.0

    # Las demás razones (índices 8-14) deben ser 0
    for i in range(8, 15):
        assert result[i] == 0.0
