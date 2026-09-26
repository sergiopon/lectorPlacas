from __future__ import annotations

from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox,
    PlateReading,
    ReviewStatus,
    VehicleType,
)
from lector_placas.domain.entities import UnverifiedReason as R
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.plate_catalog import build_test_catalog

POLICY = ConsolidationPolicy(3, 0.9, 0.6, 0.1)
BOX = BoundingBox(0, 0, 10, 10)


def rd(text: str, conf: float = 0.9) -> PlateReading:
    return PlateReading(1, 0, 0, text, (conf,) * len(text), BOX, 0.9, 1.0)


def make(confusions: ConfusionMap | None = None) -> VotingPlateConsolidator:
    return VotingPlateConsolidator(
        build_test_catalog(), POLICY, confusions or ConfusionMap.default()
    )


def test_three_way_length_tie_prefers_longest() -> None:
    result = make().consolidate([rd("ABC123"), rd("ABC12"), rd("ABC1")], VehicleType.CAR)
    assert result.text == "ABC123"
    assert R.LOW_AGREEMENT in result.reasons


def test_no_pattern_for_length() -> None:
    result = make().consolidate([rd("AB12")] * 3, VehicleType.CAR)
    assert result.format_ids == ()
    assert R.UNRECOGNIZED_FORMAT in result.reasons


def test_character_tie_resolved_by_ascii_order() -> None:
    result = make().consolidate(
        [rd("ABD123"), rd("ABC123"), rd("ABD123"), rd("ABC123")], VehicleType.CAR
    )
    assert result.text == "ABC123"


def test_empty_confusion_map_does_not_correct() -> None:
    result = make(ConfusionMap(())).consolidate([rd("ABC12S", 0.95)] * 3, VehicleType.CAR)
    assert result.text == "ABC12S"
    assert result.reasons == (R.VEHICLE_FORMAT_MISMATCH,)


def test_zero_confidence_readings() -> None:
    result = make().consolidate([rd("ABC123", 0.0)] * 3, VehicleType.CAR)
    assert result.confidence == 0.0
    assert result.status is ReviewStatus.UNVERIFIED
    assert R.LOW_CONFIDENCE in result.reasons


def test_format_ids_filtered_by_vehicle_type() -> None:
    moto = make().consolidate([rd("MCD123", 0.95)] * 3, VehicleType.MOTORCYCLE)
    car = make().consolidate([rd("MCD123", 0.95)] * 3, VehicleType.CAR)
    assert moto.format_ids == ("co_moto_diplomatica",)
    assert moto.status is ReviewStatus.CONFIRMED
    assert car.format_ids == ("co_particular_publico", "co_diplomatico_2015")
