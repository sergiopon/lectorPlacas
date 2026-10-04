"""Entidades inmutables del dominio, validadas al construirse."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from lector_placas.domain.errors import (
    InvalidBoundingBoxError,
    InvalidConfidenceError,
    InvalidEntityError,
    InvalidPlateTextError,
    PlateFormatCatalogError,
)

PLATE_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{1,10}$")
OCR_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{0,10}$")
CROP_REF_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{32}$")
FORMAT_ID_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]{1,64}$")
PATTERN_REGEX: Final[re.Pattern[str]] = re.compile(r"^[LD]{1,10}$")


def _require_unit_interval(value: float, name: str) -> None:
    """Exige un valor finito dentro de [0, 1]."""
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise InvalidConfidenceError(f"{name} fuera de [0, 1]: {value}")


def _require_non_negative_int(value: int, name: str) -> None:
    """Exige un entero mayor o igual que cero."""
    if value < 0:
        raise InvalidEntityError(f"{name} debe ser >= 0: {value}")


def _require_utc(value: datetime, name: str) -> None:
    """Exige un datetime con zona horaria UTC."""
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InvalidEntityError(f"{name} debe ser UTC con zona horaria")


class VehicleType(StrEnum):
    """Tipo de vehículo detectado."""

    CAR = "car"
    MOTORCYCLE = "motorcycle"
    BUS = "bus"
    TRUCK = "truck"


class ReviewStatus(StrEnum):
    """Estado de revisión de un avistamiento."""

    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    ILLEGIBLE = "illegible"


class UnverifiedReason(StrEnum):
    """Motivo por el que un avistamiento queda sin confirmar."""

    INSUFFICIENT_READINGS = "insufficient_readings"
    LOW_CONFIDENCE = "low_confidence"
    LOW_AGREEMENT = "low_agreement"
    UNRECOGNIZED_FORMAT = "unrecognized_format"
    UNVERIFIED_FORMAT = "unverified_format"
    VEHICLE_FORMAT_MISMATCH = "vehicle_format_mismatch"
    AMBIGUOUS_FORMAT = "ambiguous_format"
    CORRECTION_CONFLICT = "correction_conflict"
    PREDICTED_ILLEGIBLE = "predicted_illegible"
    PREDICTED_NOT_PLATE = "predicted_not_plate"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Caja alineada a ejes, esquina superior izquierda (x1, y1) e inferior derecha (x2, y2)."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        """Valida que las coordenadas sean finitas y formen un área positiva."""
        if not all(math.isfinite(value) for value in (self.x1, self.y1, self.x2, self.y2)):
            raise InvalidBoundingBoxError(
                f"coordenadas no finitas: x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2}"
            )
        if self.x1 < 0.0 or self.y1 < 0.0 or self.x2 <= self.x1 or self.y2 <= self.y1:
            raise InvalidBoundingBoxError(
                f"caja inválida: x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2}"
            )

    @property
    def width(self) -> float:
        """Ancho de la caja en píxeles."""
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        """Alto de la caja en píxeles."""
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        """Área de la caja en píxeles cuadrados."""
        return self.width * self.height

    def translate(self, dx: float, dy: float) -> BoundingBox:
        """Devuelve la caja desplazada (dx, dy)."""
        return BoundingBox(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def clip(self, frame_width: int, frame_height: int) -> BoundingBox | None:
        """Recorta la caja al marco y devuelve None si queda vacía."""
        nx1 = min(self.x1, frame_width)
        ny1 = min(self.y1, frame_height)
        nx2 = min(self.x2, frame_width)
        ny2 = min(self.y2, frame_height)
        if nx2 <= nx1 or ny2 <= ny1:
            return None
        return BoundingBox(nx1, ny1, nx2, ny2)

    def expand(self, ratio: float, frame_width: int, frame_height: int) -> BoundingBox | None:
        """Agranda la caja un `ratio` de su tamaño, recortándola al marco."""
        if not 0.0 <= ratio <= 1.0:
            raise InvalidBoundingBoxError(f"ratio fuera de [0, 1]: {ratio}")
        dx = ratio * self.width
        dy = ratio * self.height
        nx1 = max(0.0, self.x1 - dx)
        ny1 = max(0.0, self.y1 - dy)
        nx2 = min(float(frame_width), self.x2 + dx)
        ny2 = min(float(frame_height), self.y2 + dy)
        if nx2 <= nx1 or ny2 <= ny1:
            return None
        return BoundingBox(nx1, ny1, nx2, ny2)


@dataclass(frozen=True, slots=True)
class VehicleDetection:
    """Detección de un vehículo en un frame."""

    box: BoundingBox
    confidence: float
    vehicle_type: VehicleType

    def __post_init__(self) -> None:
        """Valida la confianza y el tipo de vehículo."""
        _require_unit_interval(self.confidence, "confidence")
        if not isinstance(self.vehicle_type, VehicleType):
            raise InvalidEntityError(f"vehicle_type inválido: {self.vehicle_type!r}")


@dataclass(frozen=True, slots=True)
class PlateDetection:
    """Detección de una placa en la imagen recibida por el detector."""

    box: BoundingBox
    confidence: float

    def __post_init__(self) -> None:
        """Valida la confianza de la detección."""
        _require_unit_interval(self.confidence, "confidence")


@dataclass(frozen=True, slots=True)
class TrackedVehicle:
    """Vehículo con un identificador de track asignado por el tracker."""

    track_id: int
    box: BoundingBox
    confidence: float
    vehicle_type: VehicleType

    def __post_init__(self) -> None:
        """Valida el identificador, la confianza y el tipo de vehículo."""
        _require_non_negative_int(self.track_id, "track_id")
        _require_unit_interval(self.confidence, "confidence")
        if not isinstance(self.vehicle_type, VehicleType):
            raise InvalidEntityError(f"vehicle_type inválido: {self.vehicle_type!r}")


@dataclass(frozen=True, slots=True)
class OcrResult:
    """Texto leído por el OCR y la confianza de cada carácter."""

    text: str
    char_confidences: tuple[float, ...]

    def __post_init__(self) -> None:
        """Valida el texto y la lista de confianzas."""
        if OCR_TEXT_REGEX.fullmatch(self.text) is None:
            raise InvalidPlateTextError(f"texto OCR inválido (longitud={len(self.text)})")
        _require_matching_lengths(self.text, self.char_confidences)
        for confidence in self.char_confidences:
            _require_unit_interval(confidence, "char_confidences")


@dataclass(frozen=True, slots=True)
class PlateReading:
    """Lectura OCR de la placa de un vehículo en un frame concreto."""

    track_id: int
    frame_index: int
    timestamp_ms: int
    text: str
    char_confidences: tuple[float, ...]
    plate_box: BoundingBox
    detection_confidence: float
    quality_score: float

    def __post_init__(self) -> None:
        """Valida identificadores, texto, confianzas y nitidez."""
        _require_non_negative_int(self.track_id, "track_id")
        _require_non_negative_int(self.frame_index, "frame_index")
        _require_non_negative_int(self.timestamp_ms, "timestamp_ms")
        if PLATE_TEXT_REGEX.fullmatch(self.text) is None:
            raise InvalidPlateTextError(f"texto de placa inválido (longitud={len(self.text)})")
        _require_matching_lengths(self.text, self.char_confidences)
        for confidence in self.char_confidences:
            _require_unit_interval(confidence, "char_confidences")
        _require_unit_interval(self.detection_confidence, "detection_confidence")
        if not math.isfinite(self.quality_score) or self.quality_score < 0.0:
            raise InvalidEntityError(f"quality_score debe ser finito y >= 0: {self.quality_score}")

    @property
    def mean_confidence(self) -> float:
        """Confianza media de los caracteres leídos."""
        return sum(self.char_confidences) / len(self.char_confidences)


@dataclass(frozen=True, slots=True)
class PlateFormat:
    """Entrada del catálogo de formatos de placa."""

    format_id: str
    category: str
    pattern: str
    regex: str
    verified: bool
    vehicle_types: frozenset[VehicleType]
    source: str

    def __post_init__(self) -> None:
        """Valida el identificador, el patrón, la expresión regular y la procedencia."""
        if FORMAT_ID_REGEX.fullmatch(self.format_id) is None:
            raise PlateFormatCatalogError(f"format_id inválido: {self.format_id!r}")
        if PATTERN_REGEX.fullmatch(self.pattern) is None:
            raise PlateFormatCatalogError(f"pattern inválido: {self.pattern!r}")
        _require_compilable_regex(self.regex)
        if not self.category.strip() or not self.source.strip():
            raise PlateFormatCatalogError("category y source no pueden estar vacías")
        _require_vehicle_types(self.vehicle_types)

    def matches(self, text: str) -> bool:
        """Indica si el texto encaja completo con la expresión regular del formato."""
        return re.fullmatch(self.regex, text) is not None


@dataclass(frozen=True, slots=True)
class CropQuality:
    """Medidas de calidad del mejor recorte de placa de un avistamiento."""

    plate_width_px: int
    plate_height_px: int
    sharpness: float
    contrast: float

    def __post_init__(self) -> None:
        """Valida las dimensiones, nitidez y contraste."""
        if self.plate_width_px < 1:
            raise InvalidEntityError(f"plate_width_px debe ser >= 1: {self.plate_width_px}")
        if self.plate_height_px < 1:
            raise InvalidEntityError(f"plate_height_px debe ser >= 1: {self.plate_height_px}")
        if not math.isfinite(self.sharpness) or self.sharpness < 0.0:
            raise InvalidEntityError(f"sharpness debe ser finito y >= 0: {self.sharpness}")
        if not math.isfinite(self.contrast) or self.contrast < 0.0:
            raise InvalidEntityError(f"contrast debe ser finito y >= 0: {self.contrast}")


@dataclass(frozen=True, slots=True)
class ConsolidatedPlate:
    """Resultado consolidado de las lecturas de la placa de un track."""

    text: str
    confidence: float
    agreement: float
    num_readings: int
    status: ReviewStatus
    reasons: tuple[UnverifiedReason, ...]
    format_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Valida el texto, las métricas, el estado y sus razones."""
        if PLATE_TEXT_REGEX.fullmatch(self.text) is None:
            raise InvalidPlateTextError(f"texto de placa inválido (longitud={len(self.text)})")
        _require_unit_interval(self.confidence, "confidence")
        _require_unit_interval(self.agreement, "agreement")
        if self.num_readings < 1:
            raise InvalidEntityError(f"num_readings debe ser >= 1: {self.num_readings}")
        self._require_valid_status()
        if any(FORMAT_ID_REGEX.fullmatch(format_id) is None for format_id in self.format_ids):
            raise InvalidEntityError("format_ids contiene un identificador inválido")

    def _require_valid_status(self) -> None:
        """Valida el estado de revisión y la coherencia de sus razones."""
        if self.status is ReviewStatus.CONFIRMED and self.reasons:
            raise InvalidEntityError("CONFIRMED no admite razones")
        if self.status is ReviewStatus.UNVERIFIED and not self.reasons:
            raise InvalidEntityError("UNVERIFIED exige al menos una razón")
        if self.status not in (ReviewStatus.CONFIRMED, ReviewStatus.UNVERIFIED):
            raise InvalidEntityError(f"status inválido: {self.status!r}")
        if len(set(self.reasons)) != len(self.reasons):
            raise InvalidEntityError("reasons no puede tener duplicados")


@dataclass(frozen=True, slots=True)
class Sighting:
    """Avistamiento de un track con su placa consolidada, listo para persistir."""

    run_id: int
    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    plate: ConsolidatedPlate
    crop_ref: str | None
    created_at: datetime
    quality: CropQuality | None = None

    def __post_init__(self) -> None:
        """Valida identificadores, tiempos, recorte y fecha de creación."""
        if self.run_id < 1:
            raise InvalidEntityError(f"run_id debe ser >= 1: {self.run_id}")
        _require_non_negative_int(self.track_id, "track_id")
        _require_non_negative_int(self.first_seen_ms, "first_seen_ms")
        if self.last_seen_ms < self.first_seen_ms:
            raise InvalidEntityError("last_seen_ms debe ser >= first_seen_ms")
        if self.crop_ref is not None and CROP_REF_REGEX.fullmatch(self.crop_ref) is None:
            raise InvalidEntityError("crop_ref inválido")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class SightingRecord:
    """Avistamiento persistido, tal como lo devuelve el repositorio."""

    sighting_id: int
    run_id: int
    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    ocr_text: str
    plate_text: str
    confidence: float
    agreement: float
    num_readings: int
    status: ReviewStatus
    reasons: tuple[UnverifiedReason, ...]
    format_ids: tuple[str, ...]
    crop_ref: str | None
    created_at: datetime
    reviewed_at: datetime | None
    quality: CropQuality | None = None
    duplicate_of: int | None = None

    def __post_init__(self) -> None:
        """Valida identificadores, textos, métricas, recorte y fechas."""
        _validate_sighting_record(self)


def _require_matching_lengths(text: str, char_confidences: tuple[float, ...]) -> None:
    """Exige que haya una confianza por carácter, sin exponer el texto."""
    if len(char_confidences) != len(text):
        raise InvalidEntityError(
            f"char_confidences ({len(char_confidences)}) no coincide con el texto ({len(text)})"
        )


def _require_plate_text(text: str, name: str) -> None:
    """Exige que el texto cumpla PLATE_TEXT_REGEX sin exponer su contenido."""
    if PLATE_TEXT_REGEX.fullmatch(text) is None:
        raise InvalidPlateTextError(f"{name} inválido (longitud={len(text)})")


def _require_compilable_regex(regex: str) -> None:
    """Exige que la expresión regular del formato compile."""
    try:
        re.compile(regex)
    except re.error as error:
        raise PlateFormatCatalogError(f"regex inválida: {regex!r}") from error


def _require_vehicle_types(vehicle_types: frozenset[VehicleType]) -> None:
    """Exige un conjunto no vacío formado solo por VehicleType."""
    if not vehicle_types:
        raise PlateFormatCatalogError("vehicle_types no puede estar vacío")
    if any(not isinstance(vehicle_type, VehicleType) for vehicle_type in vehicle_types):
        raise PlateFormatCatalogError("vehicle_types debe contener solo VehicleType")


def _validate_sighting_record(record: SightingRecord) -> None:
    """Valida todos los campos de un SightingRecord."""
    _validate_sighting_ids(record)
    _validate_sighting_times(record)
    _validate_sighting_plate_texts(record)
    _validate_sighting_metrics(record)
    _validate_sighting_references(record)


def _validate_sighting_ids(record: SightingRecord) -> None:
    """Valida los identificadores de un SightingRecord."""
    if record.sighting_id < 1:
        raise InvalidEntityError(f"sighting_id debe ser >= 1: {record.sighting_id}")
    if record.run_id < 1:
        raise InvalidEntityError(f"run_id debe ser >= 1: {record.run_id}")
    _require_non_negative_int(record.track_id, "track_id")


def _validate_sighting_times(record: SightingRecord) -> None:
    """Valida los timestamps de un SightingRecord."""
    _require_non_negative_int(record.first_seen_ms, "first_seen_ms")
    if record.last_seen_ms < record.first_seen_ms:
        raise InvalidEntityError("last_seen_ms debe ser >= first_seen_ms")
    _require_utc(record.created_at, "created_at")
    if record.reviewed_at is not None:
        _require_utc(record.reviewed_at, "reviewed_at")


def _validate_sighting_plate_texts(record: SightingRecord) -> None:
    """Valida los textos de placa de un SightingRecord."""
    _require_plate_text(record.ocr_text, "ocr_text")
    _require_plate_text(record.plate_text, "plate_text")


def _validate_sighting_metrics(record: SightingRecord) -> None:
    """Valida las métricas de confianza de un SightingRecord."""
    _require_unit_interval(record.confidence, "confidence")
    _require_unit_interval(record.agreement, "agreement")
    if record.num_readings < 1:
        raise InvalidEntityError(f"num_readings debe ser >= 1: {record.num_readings}")


def _validate_sighting_references(record: SightingRecord) -> None:
    """Valida las referencias a recortes y duplicados de un SightingRecord."""
    if record.crop_ref is not None and CROP_REF_REGEX.fullmatch(record.crop_ref) is None:
        raise InvalidEntityError("crop_ref inválido")
    if record.duplicate_of is not None and (
        record.duplicate_of < 1 or record.duplicate_of == record.sighting_id
    ):
        raise InvalidEntityError("duplicate_of inválido")
