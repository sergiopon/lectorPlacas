# 001 - Dominio: excepciones y entidades

## Objetivo
Implementar la jerarquía de excepciones del proyecto y las entidades inmutables del dominio con sus
validaciones.

## Depende de
000.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 regla 1 (domain solo stdlib), §6 (dataclasses frozen+slots, validación en `__post_init__`, errores propios, docstrings Google en español).
- docs/02-contratos.md §1 y §2 (firmas literales).

## Archivos a crear/modificar
- `src/lector_placas/domain/errors.py`
- `src/lector_placas/domain/entities.py`
- `tests/unit/domain/__init__.py`
- `tests/unit/domain/test_entities.py`

## Dependencias externas
Ninguna (solo stdlib).

## Interfaces y tipos involucrados
```python
# errors.py — cada clase con docstring de una línea, sin atributos extra
class LectorPlacasError(Exception): ...
class DomainError(LectorPlacasError): ...
class InvalidBoundingBoxError(DomainError): ...
class InvalidConfidenceError(DomainError): ...
class InvalidPlateTextError(DomainError): ...
class InvalidEntityError(DomainError): ...
class PlateFormatCatalogError(DomainError): ...
class ConsolidationError(DomainError): ...
class ConfigurationError(LectorPlacasError): ...
class InputValidationError(LectorPlacasError): ...
class UnsafePathError(InputValidationError): ...
class VideoSourceError(LectorPlacasError): ...
class ModelIntegrityError(LectorPlacasError): ...
class ModelLoadError(LectorPlacasError): ...
class ModelFetchError(LectorPlacasError): ...
class InferenceError(LectorPlacasError): ...
class TrackingError(LectorPlacasError): ...
class RepositoryError(LectorPlacasError): ...
class SightingNotFoundError(RepositoryError): ...
class CropStoreError(LectorPlacasError): ...
class CropNotFoundError(CropStoreError): ...
class ExportError(LectorPlacasError): ...
class EncryptionError(LectorPlacasError): ...
class KeyUnavailableError(LectorPlacasError): ...
class NetworkAccessError(LectorPlacasError): ...
class ReviewError(LectorPlacasError): ...
class EvaluationError(LectorPlacasError): ...
class DatasetError(LectorPlacasError): ...
```
```python
# entities.py
PLATE_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{1,10}$")
OCR_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{0,10}$")
CROP_REF_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{32}$")
FORMAT_ID_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]{1,64}$")
PATTERN_REGEX: Final[re.Pattern[str]] = re.compile(r"^[LD]{1,10}$")

class VehicleType(StrEnum): CAR = "car"; MOTORCYCLE = "motorcycle"; BUS = "bus"; TRUCK = "truck"
class ReviewStatus(StrEnum): CONFIRMED = "confirmed"; UNVERIFIED = "unverified"; REJECTED = "rejected"; CORRECTED = "corrected"
class UnverifiedReason(StrEnum):
    INSUFFICIENT_READINGS = "insufficient_readings"; LOW_CONFIDENCE = "low_confidence"
    LOW_AGREEMENT = "low_agreement"; UNRECOGNIZED_FORMAT = "unrecognized_format"
    UNVERIFIED_FORMAT = "unverified_format"; VEHICLE_FORMAT_MISMATCH = "vehicle_format_mismatch"
    AMBIGUOUS_FORMAT = "ambiguous_format"

@dataclass(frozen=True, slots=True)
class BoundingBox:
    x1: float; y1: float; x2: float; y2: float
    @property
    def width(self) -> float: ...
    @property
    def height(self) -> float: ...
    @property
    def area(self) -> float: ...
    def translate(self, dx: float, dy: float) -> BoundingBox: ...
    def clip(self, frame_width: int, frame_height: int) -> BoundingBox | None: ...
    def expand(self, ratio: float, frame_width: int, frame_height: int) -> BoundingBox | None: ...

@dataclass(frozen=True, slots=True)
class VehicleDetection: box: BoundingBox; confidence: float; vehicle_type: VehicleType
@dataclass(frozen=True, slots=True)
class PlateDetection: box: BoundingBox; confidence: float
@dataclass(frozen=True, slots=True)
class TrackedVehicle: track_id: int; box: BoundingBox; confidence: float; vehicle_type: VehicleType
@dataclass(frozen=True, slots=True)
class OcrResult: text: str; char_confidences: tuple[float, ...]
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
@dataclass(frozen=True, slots=True)
class Sighting:
    run_id: int; track_id: int; first_seen_ms: int; last_seen_ms: int
    vehicle_type: VehicleType; plate: ConsolidatedPlate; crop_ref: str | None; created_at: datetime
@dataclass(frozen=True, slots=True)
class SightingRecord:
    sighting_id: int; run_id: int; track_id: int; first_seen_ms: int; last_seen_ms: int
    vehicle_type: VehicleType; ocr_text: str; plate_text: str; confidence: float; agreement: float
    num_readings: int; status: ReviewStatus; reasons: tuple[UnverifiedReason, ...]
    format_ids: tuple[str, ...]; crop_ref: str | None; created_at: datetime; reviewed_at: datetime | None
```
(En el archivo real cada campo va en su propia línea y cada clase lleva docstring.)

## Comportamiento esperado
1. Helpers privados de módulo:
   - `_require_unit_interval(value: float, name: str) -> None`: si no es finito o no está en [0, 1] → `InvalidConfidenceError(f"{name} fuera de [0, 1]: {value}")`.
   - `_require_non_negative_int(value: int, name: str) -> None`: si `value < 0` → `InvalidEntityError(f"{name} debe ser >= 0: {value}")`.
   - `_require_utc(value: datetime, name: str) -> None`: si `value.tzinfo is None` o `value.utcoffset() != timedelta(0)` → `InvalidEntityError(f"{name} debe ser UTC con zona horaria")`.
2. `BoundingBox.__post_init__`: si algún valor no es finito, `x1 < 0`, `y1 < 0`, `x2 <= x1` o `y2 <= y1` → `InvalidBoundingBoxError`.
   `width = x2 - x1`, `height = y2 - y1`, `area = width * height`.
3. `translate(dx, dy)` devuelve una nueva caja desplazada (puede lanzar `InvalidBoundingBoxError` si queda con coordenadas negativas).
4. `clip(w, h)`: `nx1 = min(x1, w)`, `ny1 = min(y1, h)`, `nx2 = min(x2, w)`, `ny2 = min(y2, h)`; si `nx2 <= nx1` o `ny2 <= ny1` → `None`; si no, nueva caja.
5. `expand(ratio, w, h)`: si `ratio` no está en [0, 1] → `InvalidBoundingBoxError`. `dx = ratio * width`, `dy = ratio * height`;
   `nx1 = max(0.0, x1 - dx)`, `ny1 = max(0.0, y1 - dy)`, `nx2 = min(float(w), x2 + dx)`, `ny2 = min(float(h), y2 + dy)`;
   si `nx2 <= nx1` o `ny2 <= ny1` → `None`; si no, nueva caja.
6. `VehicleDetection`/`PlateDetection`/`TrackedVehicle`: validan confianza con `_require_unit_interval(..., "confidence")`;
   `TrackedVehicle.track_id` con `_require_non_negative_int`; `vehicle_type` debe ser instancia de `VehicleType`, si no `InvalidEntityError`.
7. `OcrResult`: `text` debe cumplir `OCR_TEXT_REGEX` (si no `InvalidPlateTextError`); `len(char_confidences) != len(text)` → `InvalidEntityError`; cada confianza en [0, 1].
8. `PlateReading`: enteros no negativos; `text` cumple `PLATE_TEXT_REGEX` (si no `InvalidPlateTextError`); longitudes iguales (si no `InvalidEntityError`); confianzas en [0, 1]; `quality_score` finito y ≥ 0 (si no `InvalidEntityError`).
   `mean_confidence = sum(char_confidences) / len(char_confidences)`.
9. `PlateFormat`: `format_id` cumple `FORMAT_ID_REGEX`; `pattern` cumple `PATTERN_REGEX`; `regex` compila (`re.error` → `PlateFormatCatalogError ... from e`);
   `category.strip()` y `source.strip()` no vacíos; `vehicle_types` no vacío y todos `VehicleType`. Cualquier violación → `PlateFormatCatalogError`.
   `matches(text)` = `re.fullmatch(self.regex, text) is not None`.
10. `ConsolidatedPlate`: `text` cumple `PLATE_TEXT_REGEX`; confianza y acuerdo en [0, 1]; `num_readings >= 1`;
    `status` ∈ {CONFIRMED, UNVERIFIED}; CONFIRMED exige `reasons == ()`; UNVERIFIED exige `reasons` no vacío;
    `reasons` sin duplicados; cada `format_id` cumple `FORMAT_ID_REGEX`. Violaciones de estado/razones/ids → `InvalidEntityError`.
11. `Sighting`: `run_id >= 1`, `track_id >= 0`, `first_seen_ms >= 0`, `last_seen_ms >= first_seen_ms`, `crop_ref` `None` o `CROP_REF_REGEX`, `created_at` UTC. Violaciones → `InvalidEntityError`.
12. `SightingRecord`: `sighting_id >= 1`, `run_id >= 1`, `track_id >= 0`, `last_seen_ms >= first_seen_ms >= 0`, `ocr_text` y `plate_text` cumplen `PLATE_TEXT_REGEX` (si no `InvalidPlateTextError`), confianza y acuerdo en [0, 1], `num_readings >= 1`, `crop_ref` válido o `None`, `created_at` UTC, `reviewed_at` `None` o UTC.

## Casos borde y manejo de errores
- `float("nan")` o `float("inf")` en cualquier coordenada o confianza → error correspondiente.
- Una caja de ancho 0 es inválida.
- Mensajes en español y sin texto de placa en claro (no incluyas `text` en mensajes de error de `PlateReading`, `OcrResult`, `ConsolidatedPlate`, `SightingRecord`; usa solo la longitud).

## Tests de aceptación
```python
# tests/unit/domain/test_entities.py
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from lector_placas.domain.entities import (
    BoundingBox, ConsolidatedPlate, OcrResult, PlateDetection, PlateFormat, PlateReading,
    ReviewStatus, Sighting, SightingRecord, TrackedVehicle, UnverifiedReason, VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import (
    DomainError, InvalidBoundingBoxError, InvalidConfidenceError, InvalidEntityError,
    InvalidPlateTextError, LectorPlacasError, PlateFormatCatalogError, UnsafePathError,
    InputValidationError, SightingNotFoundError, RepositoryError, CropNotFoundError, CropStoreError,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def make_box() -> BoundingBox:
    return BoundingBox(10.0, 20.0, 110.0, 70.0)


def make_plate(**overrides: object) -> ConsolidatedPlate:
    values: dict[str, object] = dict(
        text="ABC123", confidence=0.95, agreement=1.0, num_readings=3,
        status=ReviewStatus.CONFIRMED, reasons=(), format_ids=("co_particular_publico",),
    )
    values.update(overrides)
    return ConsolidatedPlate(**values)  # type: ignore[arg-type]


def test_error_hierarchy() -> None:
    assert issubclass(DomainError, LectorPlacasError)
    assert issubclass(InvalidBoundingBoxError, DomainError)
    assert issubclass(UnsafePathError, InputValidationError)
    assert issubclass(SightingNotFoundError, RepositoryError)
    assert issubclass(CropNotFoundError, CropStoreError)


def test_bounding_box_properties() -> None:
    box = make_box()
    assert (box.width, box.height, box.area) == (100.0, 50.0, 5000.0)


@pytest.mark.parametrize("coords", [
    (0, 0, 0, 10), (0, 0, 10, 0), (-1, 0, 10, 10), (0, -1, 10, 10),
    (5, 0, 4, 10), (0, 0, math.nan, 10), (0, 0, math.inf, 10),
])
def test_bounding_box_rejects_invalid(coords: tuple[float, float, float, float]) -> None:
    with pytest.raises(InvalidBoundingBoxError):
        BoundingBox(*coords)


def test_bounding_box_translate() -> None:
    assert make_box().translate(5, -10) == BoundingBox(15.0, 10.0, 115.0, 60.0)


def test_bounding_box_clip_inside_and_outside() -> None:
    assert BoundingBox(10, 10, 300, 300).clip(200, 100) == BoundingBox(10, 10, 200, 100)
    assert BoundingBox(250, 10, 300, 50).clip(200, 100) is None


def test_bounding_box_expand_is_clipped() -> None:
    expanded = BoundingBox(10, 10, 110, 60).expand(0.1, 115, 1000)
    assert expanded == BoundingBox(0.0, 5.0, 115.0, 65.0)


def test_bounding_box_expand_rejects_bad_ratio() -> None:
    with pytest.raises(InvalidBoundingBoxError):
        make_box().expand(1.5, 100, 100)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, math.nan])
def test_detection_rejects_bad_confidence(confidence: float) -> None:
    with pytest.raises(InvalidConfidenceError):
        VehicleDetection(make_box(), confidence, VehicleType.CAR)
    with pytest.raises(InvalidConfidenceError):
        PlateDetection(make_box(), confidence)


def test_tracked_vehicle_rejects_negative_id() -> None:
    with pytest.raises(InvalidEntityError):
        TrackedVehicle(-1, make_box(), 0.9, VehicleType.CAR)


def test_ocr_result_allows_empty_text() -> None:
    assert OcrResult("", ()).text == ""


@pytest.mark.parametrize("text", ["abc123", "ABC-12", "ABCDEFGHIJK"])
def test_ocr_result_rejects_bad_text(text: str) -> None:
    with pytest.raises(InvalidPlateTextError):
        OcrResult(text, tuple(0.9 for _ in text))


def test_ocr_result_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidEntityError):
        OcrResult("ABC", (0.9, 0.9))


def test_plate_reading_mean_confidence() -> None:
    reading = PlateReading(1, 2, 3, "AB", (0.5, 1.0), make_box(), 0.8, 10.0)
    assert reading.mean_confidence == pytest.approx(0.75)


def test_plate_reading_rejects_empty_text_and_negative_quality() -> None:
    with pytest.raises(InvalidPlateTextError):
        PlateReading(1, 2, 3, "", (), make_box(), 0.8, 1.0)
    with pytest.raises(InvalidEntityError):
        PlateReading(1, 2, 3, "AB", (0.5, 0.5), make_box(), 0.8, -1.0)


def test_plate_format_matches_full_text() -> None:
    fmt = PlateFormat("co_moto", "Moto", "LLLDDL", "^[A-Z]{3}[0-9]{2}[A-Z]$", True,
                      frozenset({VehicleType.MOTORCYCLE}), "Res. 4923/1994")
    assert fmt.matches("XYZ98K")
    assert not fmt.matches("XYZ98KK")


@pytest.mark.parametrize("field,value", [
    ("format_id", "Co-Moto"), ("pattern", "LLX"), ("regex", "[A-Z"),
    ("category", " "), ("source", ""), ("vehicle_types", frozenset()),
])
def test_plate_format_rejects_invalid(field: str, value: object) -> None:
    values: dict[str, object] = dict(
        format_id="co_moto", category="Moto", pattern="LLLDDL", regex="^[A-Z]{3}$", verified=True,
        vehicle_types=frozenset({VehicleType.MOTORCYCLE}), source="fuente",
    )
    values[field] = value
    with pytest.raises(PlateFormatCatalogError):
        PlateFormat(**values)  # type: ignore[arg-type]


def test_consolidated_plate_status_rules() -> None:
    with pytest.raises(InvalidEntityError):
        make_plate(reasons=(UnverifiedReason.LOW_CONFIDENCE,))
    with pytest.raises(InvalidEntityError):
        make_plate(status=ReviewStatus.UNVERIFIED, reasons=())
    with pytest.raises(InvalidEntityError):
        make_plate(status=ReviewStatus.REJECTED)
    with pytest.raises(InvalidEntityError):
        make_plate(status=ReviewStatus.UNVERIFIED,
                   reasons=(UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_CONFIDENCE))
    ok = make_plate(status=ReviewStatus.UNVERIFIED, reasons=(UnverifiedReason.LOW_AGREEMENT,))
    assert ok.status is ReviewStatus.UNVERIFIED


def test_sighting_requires_utc_and_valid_times() -> None:
    plate = make_plate()
    Sighting(1, 0, 100, 200, VehicleType.CAR, plate, "0" * 32, NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 300, 200, VehicleType.CAR, plate, None, NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 100, 200, VehicleType.CAR, plate, None, NOW.replace(tzinfo=None))
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 100, 200, VehicleType.CAR, plate, None,
                 NOW.astimezone(timezone(timedelta(hours=-5))))
    with pytest.raises(InvalidEntityError):
        Sighting(1, 0, 100, 200, VehicleType.CAR, plate, "XYZ", NOW)
    with pytest.raises(InvalidEntityError):
        Sighting(0, 0, 100, 200, VehicleType.CAR, plate, None, NOW)


def test_sighting_record_validates_texts() -> None:
    SightingRecord(1, 1, 0, 0, 10, VehicleType.CAR, "ABC123", "ABC128", 0.9, 0.8, 3,
                   ReviewStatus.CORRECTED, (), ("co_particular_publico",), None, NOW, NOW)
    with pytest.raises(InvalidPlateTextError):
        SightingRecord(1, 1, 0, 0, 10, VehicleType.CAR, "abc", "ABC128", 0.9, 0.8, 3,
                       ReviewStatus.CORRECTED, (), (), None, NOW, None)
```

## Fuera de alcance
Catálogo de formatos (002), corrección (003), consolidación (004), `mask_plate` (spec 004).

## Definition of Done
- [ ] `uv run pytest tests/unit/domain/test_entities.py tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `domain/` no importa nada fuera de la stdlib.
