# 004 - Dominio: consolidación por votación y enmascarado de placas

## Objetivo
Implementar `VotingPlateConsolidator` (algoritmo normativo de ADR-007) que convierte las lecturas de
un track en un `ConsolidatedPlate` con estado `confirmed`/`unverified` y razones, y `mask_plate`.

## Depende de
001, 002, 003.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 regla 1, §6 (funciones ≤ 20 sentencias: divide en helpers privados).
- ADR-007 (algoritmo), requisitos RF-10..RF-17, M-01. SEG-05 (`mask_plate`).
- docs/02-contratos.md §2, §3.

## Archivos a crear/modificar
- `src/lector_placas/domain/consolidation.py`
- `src/lector_placas/domain/privacy.py`
- `tests/unit/domain/test_consolidation.py`
- `tests/unit/domain/test_privacy.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
```python
# de domain/entities.py (spec 001)
class VehicleType(StrEnum): CAR = "car"; MOTORCYCLE = "motorcycle"; BUS = "bus"; TRUCK = "truck"
class ReviewStatus(StrEnum): CONFIRMED = "confirmed"; UNVERIFIED = "unverified"; REJECTED = "rejected"; CORRECTED = "corrected"
class UnverifiedReason(StrEnum):   # el orden de declaración es el orden canónico de las razones
    INSUFFICIENT_READINGS = "insufficient_readings"; LOW_CONFIDENCE = "low_confidence"
    LOW_AGREEMENT = "low_agreement"; UNRECOGNIZED_FORMAT = "unrecognized_format"
    UNVERIFIED_FORMAT = "unverified_format"; VEHICLE_FORMAT_MISMATCH = "vehicle_format_mismatch"
    AMBIGUOUS_FORMAT = "ambiguous_format"
@dataclass(frozen=True, slots=True)
class PlateReading:
    track_id: int; frame_index: int; timestamp_ms: int; text: str
    char_confidences: tuple[float, ...]; plate_box: BoundingBox
    detection_confidence: float; quality_score: float
    @property
    def mean_confidence(self) -> float: ...
@dataclass(frozen=True, slots=True)
class PlateFormat:
    format_id: str; category: str; pattern: str; regex: str; verified: bool
    vehicle_types: frozenset[VehicleType]; source: str
    def matches(self, text: str) -> bool: ...
@dataclass(frozen=True, slots=True)
class ConsolidatedPlate:
    text: str; confidence: float; agreement: float; num_readings: int
    status: ReviewStatus; reasons: tuple[UnverifiedReason, ...]; format_ids: tuple[str, ...]
# de domain/plate_formats.py (spec 002)
class PlateFormatCatalog:
    def patterns_of_length(self, length: int) -> tuple[str, ...]: ...   # ordenados alfabéticamente
    def matching_with_pattern(self, text: str, pattern: str) -> tuple[PlateFormat, ...]: ...
# de domain/ocr_correction.py (spec 003)
class ConfusionMap: ...   # ConfusionMap.default()
def correct_to_pattern(text: str, pattern: str, confusions: ConfusionMap) -> str: ...
# de domain/errors.py
class ConsolidationError(DomainError): ...
class InvalidEntityError(DomainError): ...
```
```python
# domain/consolidation.py — a implementar
@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    min_readings: int
    confirm_threshold: float
    min_agreement: float
    ambiguity_margin: float

class VotingPlateConsolidator:
    def __init__(self, catalog: PlateFormatCatalog, policy: ConsolidationPolicy,
                 confusions: ConfusionMap) -> None: ...
    def consolidate(self, readings: Sequence[PlateReading],
                    vehicle_type: VehicleType) -> ConsolidatedPlate: ...

# domain/privacy.py — a implementar
def mask_plate(text: str) -> str: ...
```

## Comportamiento esperado
1. `ConsolidationPolicy.__post_init__`: `min_readings >= 1`; los otros tres en [0, 1]. Si no → `InvalidEntityError`.
2. `consolidate` — validación: `readings` vacío → `ConsolidationError("no hay lecturas para consolidar")`;
   más de un `track_id` distinto → `ConsolidationError("lecturas de tracks distintos")`.
3. **Longitud objetivo `L`**: sumar `mean_confidence` por longitud de texto. `L` = longitud con la suma máxima.
   Si varias longitudes empatan (`math.isclose(a, b, rel_tol=1e-9)` con el máximo) → `L` = la mayor de ellas y se
   marca `length_tie = True`.
4. **Grupo**: lecturas con `len(text) == L`, en el orden recibido; `n = len(grupo)`.
5. **Voto** (helper `_vote(textos: list[str], confianzas: list[tuple[float, ...]], length: int) -> tuple[str, float, float]`):
   por posición `i`, suma de `confianzas[j][i]` agrupada por carácter `textos[j][i]`; ganador = mayor suma, empate →
   carácter con menor orden (`min` por `(-suma, carácter)`); `score_i = suma_ganador / n`.
   Texto = concatenación de ganadores; `confidence = min(score_i)`; `agreement = (#textos == texto) / n`.
6. **Evaluación por patrón**: para cada `P` en `catalog.patterns_of_length(L)` (orden alfabético): corregir cada texto
   del grupo con `correct_to_pattern(texto, P, confusions)` (las confianzas no cambian), votar, y obtener
   `formatos = catalog.matching_with_pattern(texto_P, P)`. Si `formatos` no está vacío, se **conserva**
   `(P, texto_P, confidence_P, agreement_P, formatos)`.
7. **Selección**:
   a. Si no hay patrones de longitud `L` o no se conservó ninguno: voto sobre los textos **sin corregir**; razones
      `{UNRECOGNIZED_FORMAT}`; `format_ids = ()`.
   b. Compatibles = conservados con algún formato cuyo `vehicle_types` contiene `vehicle_type`.
      Si no hay compatibles: el conservado de mayor `confidence` (empate → el primero en orden de patrón);
      razones `{VEHICLE_FORMAT_MISMATCH}`; `format_ids` = ids de todos sus formatos.
   c. Si hay compatibles: ordenarlos por `confidence` descendente con orden estable (empates conservan el orden de patrón);
      el primero es el elegido; `format_ids` = ids de sus formatos compatibles con `vehicle_type` (orden del catálogo).
      Si existe un segundo y `confidence_1 - confidence_2 < ambiguity_margin` → razón `AMBIGUOUS_FORMAT`.
      Si ninguno de sus formatos compatibles tiene `verified = True` → razón `UNVERIFIED_FORMAT`.
8. **Razones adicionales**: `length_tie` → `LOW_AGREEMENT`; `n < min_readings` → `INSUFFICIENT_READINGS`;
   `confidence < confirm_threshold` → `LOW_CONFIDENCE`; `agreement < min_agreement` → `LOW_AGREEMENT`.
9. **Resultado**: `reasons` = tupla sin duplicados ordenada según el orden de declaración de `UnverifiedReason`.
   `status = CONFIRMED` si `reasons` está vacío, si no `UNVERIFIED`. `num_readings = n`.
   Devuelve `ConsolidatedPlate(text, confidence, agreement, n, status, reasons, format_ids)`.
10. `mask_plate(text)`: `len(text) <= 2` → `"*" * len(text)`; si no → `text[0] + "*" * (len(text) - 2) + text[-1]`.

## Casos borde y manejo de errores
- No registrar (logging) texto de placa en este módulo; el dominio no hace logging.
- `confidence` y `agreement` quedan en [0, 1] por construcción (cada confianza ≤ 1).

## Tests de aceptación
```python
# tests/unit/domain/test_consolidation.py
from __future__ import annotations

import pytest

from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox, PlateReading, ReviewStatus, UnverifiedReason as R, VehicleType,
)
from lector_placas.domain.errors import ConsolidationError, InvalidEntityError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.plate_catalog import build_test_catalog

POLICY = ConsolidationPolicy(min_readings=3, confirm_threshold=0.90, min_agreement=0.60,
                             ambiguity_margin=0.10)
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
        "XYZ98K", ReviewStatus.CONFIRMED, ("co_moto",))


def test_vehicle_type_disambiguates_correction() -> None:
    readings = [rd("ABC12S", 0.95), rd("ABC125", 0.95), rd("ABC125", 0.95)]
    car = consolidator().consolidate(readings, VehicleType.CAR)
    moto = consolidator().consolidate(readings, VehicleType.MOTORCYCLE)
    assert (car.text, car.status) == ("ABC125", ReviewStatus.CONFIRMED)
    assert (moto.text, moto.status, moto.format_ids) == (
        "ABC12S", ReviewStatus.CONFIRMED, ("co_moto",))
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
```
```python
# tests/unit/domain/test_privacy.py
from __future__ import annotations

import pytest

from lector_placas.domain.privacy import mask_plate


@pytest.mark.parametrize("text,expected", [
    ("ABC123", "A****3"), ("XYZ98K", "X****K"), ("AB", "**"), ("A", "*"), ("", ""),
])
def test_mask_plate(text: str, expected: str) -> None:
    assert mask_plate(text) == expected
```

## Fuera de alcance
Selección de lecturas y del mejor recorte (spec 023); persistencia.

## Definition of Done
- [ ] `uv run pytest tests/unit/domain tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] Ninguna función supera 20 sentencias ni complejidad 8.
