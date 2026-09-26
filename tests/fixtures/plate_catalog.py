from __future__ import annotations

from lector_placas.domain.entities import PlateFormat, VehicleType
from lector_placas.domain.plate_formats import PlateFormatCatalog

_ALL = frozenset(VehicleType)
_CARS = frozenset({VehicleType.CAR, VehicleType.BUS, VehicleType.TRUCK})
_MOTO = frozenset({VehicleType.MOTORCYCLE})

_ROWS: tuple[tuple[str, str, str, bool, frozenset[VehicleType]], ...] = (
    ("co_particular_publico", "LLLDDD", r"^[A-Z]{3}[0-9]{3}$", True, _CARS),
    ("co_diplomatico_2015", "LLLDDD", r"^[MDCAO][A-Z]{2}[0-9]{3}$", True, _CARS),
    ("co_moto_diplomatica", "LLLDDD", r"^MCD[0-9]{3}$", True, _MOTO),
    ("co_moto", "LLLDDL", r"^[A-Z]{3}[0-9]{2}[A-Z]$", True, _MOTO),
    ("co_moto_antigua", "LLLDD", r"^[A-Z]{3}[0-9]{2}$", True, _MOTO),
    ("co_motocarro", "DDDLLL", r"^[0-9]{3}[A-Z]{3}$", True, _ALL),
    ("co_diplomatico_antiguo", "LLDDDD", r"^(CD|CC|AT|OI)[0-9]{4}$", True, _CARS),
    ("co_remolque", "LDDDDD", r"^[RS][0-9]{5}$", False, _ALL),
    ("co_importacion_temporal", "LDDDD", r"^T[0-9]{4}$", False, _ALL),
)


def build_test_catalog() -> PlateFormatCatalog:
    return PlateFormatCatalog(
        [
            PlateFormat(fid, fid, pattern, regex, verified, types, "fixture sintético")
            for fid, pattern, regex, verified, types in _ROWS
        ]
    )
