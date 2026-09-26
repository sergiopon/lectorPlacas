from __future__ import annotations

import pytest

from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox,
    PlateReading,
    ReviewStatus,
    VehicleType,
)
from lector_placas.domain.entities import UnverifiedReason as R
from lector_placas.domain.errors import ConsolidationError, InvalidEntityError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.plate_catalog import build_test_catalog

POLICY = ConsolidationPolicy(
    min_readings=3, confirm_threshold=0.90, min_agreement=0.60, ambiguity_margin=0.10
)
BOX = BoundingBox(0, 0, 100, 30)


def rd(text: str, conf: float = 0.99, track: int = 1) -> PlateReading:
    return PlateReading(track, 0, 0, text, tuple(conf for _ in text), BOX, 0.9, 10.0)


def consolidator() -> VotingPlateConsolidator:
    return VotingPlateConsolidator(build_test_catalog(), POLICY, ConfusionMap.default())


def test_confirms_car_plate() -> None:
    result = consolidator().consolidate([rd("ABC123")] * 3, VehicleType.CAR)
    assert result.text == "ABC123"
    assert result.status is ReviewStatus.CONFIRMED
    assert result.reasons == ()
    assert result.confidence == pytest.approx(0.99)
    assert result.agreement == 1.0
    assert result.num_readings == 3
    assert result.format_ids == ("co_particular_publico", "co_diplomatico_2015")


def test_confirms_moto_plate() -> None:
    result = consolidator().consolidate([rd("XYZ98K", 0.97)] * 3, VehicleType.MOTORCYCLE)
    assert (result.text, result.status, result.format_ids) == (
        "XYZ98K",
        ReviewStatus.CONFIRMED,
        ("co_moto",),
    )


def test_vehicle_type_disambiguates_correction() -> None:
    readings = [rd("ABC12S", 0.95), rd("ABC125", 0.95), rd("ABC125", 0.95)]
    car = consolidator().consolidate(readings, VehicleType.CAR)
    moto = consolidator().consolidate(readings, VehicleType.MOTORCYCLE)
    assert (car.text, car.status) == ("ABC125", ReviewStatus.CONFIRMED)
    assert (moto.text, moto.status, moto.format_ids) == (
        "ABC12S",
        ReviewStatus.CONFIRMED,
        ("co_moto",),
    )
    assert car.agreement == 1.0


def test_vehicle_format_mismatch() -> None:
    result = consolidator().consolidate([rd("XYZ98K")] * 3, VehicleType.CAR)
    assert result.status is ReviewStatus.UNVERIFIED
    assert result.reasons == (R.VEHICLE_FORMAT_MISMATCH,)
    assert result.format_ids == ("co_moto",)


def test_unverified_format_is_never_confirmed() -> None:
    result = consolidator().consolidate([rd("R12345")] * 3, VehicleType.TRUCK)
    assert (result.text, result.reasons) == ("R12345", (R.UNVERIFIED_FORMAT,))
    assert result.format_ids == ("co_remolque",)


def test_insufficient_readings() -> None:
    result = consolidator().consolidate([rd("ABC123")] * 2, VehicleType.CAR)
    assert result.reasons == (R.INSUFFICIENT_READINGS,)


def test_low_confidence() -> None:
    result = consolidator().consolidate([rd("ABC123", 0.5)] * 3, VehicleType.CAR)
    assert result.reasons == (R.LOW_CONFIDENCE,)
    assert result.confidence == pytest.approx(0.5)


def test_low_agreement_and_confidence() -> None:
    readings = [rd("ABC123"), rd("ABC123"), rd("ABD123"), rd("ABE123"), rd("ABF123")]
    result = consolidator().consolidate(readings, VehicleType.CAR)
    assert result.text == "ABC123"
    assert result.agreement == pytest.approx(0.4)
    assert result.confidence == pytest.approx(1.98 / 5)
    assert result.reasons == (R.LOW_CONFIDENCE, R.LOW_AGREEMENT)


def test_unrecognized_length_uses_weighted_raw_vote() -> None:
    readings = [rd("AB12", 0.4), rd("AB12", 0.4), rd("AB13", 0.95)]
    result = consolidator().consolidate(readings, VehicleType.CAR)
    assert result.text == "AB13"
    assert result.format_ids == ()
    assert result.confidence == pytest.approx(0.95 / 3)
    assert result.reasons == (R.LOW_CONFIDENCE, R.LOW_AGREEMENT, R.UNRECOGNIZED_FORMAT)


def test_target_length_by_confidence_mass() -> None:
    readings = [rd("ABC123", 0.9), rd("ABC123", 0.9), rd("ABC12", 0.9)]
    result = consolidator().consolidate(readings, VehicleType.CAR)
    assert (result.text, result.num_readings) == ("ABC123", 2)
    assert result.reasons == (R.INSUFFICIENT_READINGS,)


def test_length_tie_prefers_longer_and_flags() -> None:
    result = consolidator().consolidate([rd("ABC123", 0.9), rd("ABC12", 0.9)], VehicleType.CAR)
    assert result.text == "ABC123"
    assert result.reasons == (R.INSUFFICIENT_READINGS, R.LOW_AGREEMENT)


def test_ambiguous_patterns_flagged() -> None:
    result = consolidator().consolidate([rd("OI8BOS")] * 3, VehicleType.TRUCK)
    assert result.text == "018BOS"
    assert result.format_ids == ("co_motocarro",)
    assert result.reasons == (R.AMBIGUOUS_FORMAT,)


def test_errors() -> None:
    with pytest.raises(ConsolidationError):
        consolidator().consolidate([], VehicleType.CAR)
    with pytest.raises(ConsolidationError):
        consolidator().consolidate([rd("ABC123", track=1), rd("ABC123", track=2)], VehicleType.CAR)
    with pytest.raises(InvalidEntityError):
        ConsolidationPolicy(0, 0.9, 0.6, 0.1)
    with pytest.raises(InvalidEntityError):
        ConsolidationPolicy(3, 1.5, 0.6, 0.1)
