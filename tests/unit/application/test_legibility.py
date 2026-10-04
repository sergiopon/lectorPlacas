from __future__ import annotations

import pytest

from lector_placas.application.legibility import (
    LegibilityModel,
    feature_vector,
    legibility_reason,
    predict,
)
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    CropQuality,
    ReviewStatus,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import InvalidEntityError


def make_plate(reasons: tuple[UnverifiedReason, ...]) -> ConsolidatedPlate:
    return ConsolidatedPlate("ABC123", 0.8, 0.75, 4, ReviewStatus.UNVERIFIED, reasons, ())


def make_model(bias: tuple[float, float, float], threshold: float = 0.5) -> LegibilityModel:
    return LegibilityModel((0.0,) * 16, (1.0,) * 16, ((0.0,) * 16,) * 3, bias, threshold)


FEATURES = (0.0,) * 16


def test_feature_vector_reference() -> None:
    vector = feature_vector(
        make_plate((UnverifiedReason.LOW_CONFIDENCE,)),
        CropQuality(60, 20, 99.0, 64.0),
        1920,
        1080,
        VehicleType.CAR,
    )
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
    assert list(vector) == pytest.approx(expected)


def test_predicted_reasons_are_not_features() -> None:
    quality = CropQuality(60, 20, 99.0, 64.0)
    with_predicted = feature_vector(
        make_plate((UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.PREDICTED_ILLEGIBLE)),
        quality,
        1920,
        1080,
        VehicleType.CAR,
    )
    without = feature_vector(
        make_plate((UnverifiedReason.LOW_CONFIDENCE,)), quality, 1920, 1080, VehicleType.CAR
    )
    assert with_predicted == without


def test_predict_uniform() -> None:
    assert predict(make_model((0.0, 0.0, 0.0)), FEATURES) == pytest.approx((1 / 3, 1 / 3, 1 / 3))


def test_legibility_reason() -> None:
    cases = [
        ((0.0, 0.0, 0.0), UnverifiedReason.PREDICTED_ILLEGIBLE),
        ((0.0, 0.0, 1.0), UnverifiedReason.PREDICTED_NOT_PLATE),
        ((0.0, 1.0, 0.0), UnverifiedReason.PREDICTED_ILLEGIBLE),
        ((5.0, 0.0, 0.0), None),
    ]
    for bias, expected in cases:
        assert legibility_reason(make_model(bias), FEATURES) is expected


def test_invalid_model() -> None:
    zero = (0.0,) * 16
    weights = (zero,) * 3
    bias = (0.0, 0.0, 0.0)
    with pytest.raises(InvalidEntityError):
        LegibilityModel((0.0,) * 15, (1.0,) * 16, weights, bias, 0.5)
    with pytest.raises(InvalidEntityError):
        LegibilityModel(zero, (1.0,) * 15 + (0.0,), weights, bias, 0.5)
    with pytest.raises(InvalidEntityError):
        LegibilityModel(zero, (1.0,) * 16, weights, bias, 1.0)
