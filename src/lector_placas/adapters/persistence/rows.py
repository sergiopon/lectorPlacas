"""Conversión de filas y fechas compartida por los adaptadores de persistencia."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from lector_placas.domain.entities import (
    ReviewStatus,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)

# Columnas del SELECT de avistamientos, en el mismo orden que `row_to_record`.
SIGHTING_COLUMNS: Final[str] = (
    "sighting_id, run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, "
    "ocr_text, plate_text, confidence, agreement, num_readings, status, reasons, "
    "format_ids, crop_ref, created_at, reviewed_at"
)


def to_db_time(value: datetime) -> str:
    """Convierte un `datetime` a su representación ISO-8601 UTC con microsegundos.

    Args:
        value: fecha a convertir.

    Returns:
        Texto ISO-8601 en UTC con microsegundos.
    """
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def from_db_time(value: str) -> datetime:
    """Convierte una fecha ISO-8601 almacenada en su `datetime` equivalente.

    Args:
        value: texto ISO-8601 leído de la base de datos.

    Returns:
        `datetime` reconstruido.
    """
    return datetime.fromisoformat(value)


def row_to_record(row: tuple[Any, ...]) -> SightingRecord:
    """Convierte una fila de `sightings` en un `SightingRecord`.

    Args:
        row: fila con las columnas de `SIGHTING_COLUMNS`, en ese orden.

    Returns:
        El avistamiento correspondiente a la fila.
    """
    (
        sighting_id,
        run_id,
        track_id,
        first_seen_ms,
        last_seen_ms,
        vehicle_type,
        ocr_text,
        plate_text,
        confidence,
        agreement,
        num_readings,
        status,
        reasons,
        format_ids,
        crop_ref,
        created_at,
        reviewed_at,
    ) = row
    return SightingRecord(
        sighting_id,
        run_id,
        track_id,
        first_seen_ms,
        last_seen_ms,
        VehicleType(vehicle_type),
        ocr_text,
        plate_text,
        confidence,
        agreement,
        num_readings,
        ReviewStatus(status),
        _split_reasons(reasons),
        _split_format_ids(format_ids),
        crop_ref,
        from_db_time(created_at),
        from_db_time(reviewed_at) if reviewed_at is not None else None,
    )


def _split_reasons(value: str) -> tuple[UnverifiedReason, ...]:
    """Divide la columna `reasons` en su tupla de motivos."""
    if not value:
        return ()
    return tuple(UnverifiedReason(item) for item in value.split(","))


def _split_format_ids(value: str) -> tuple[str, ...]:
    """Divide la columna `format_ids` en su tupla de identificadores."""
    if not value:
        return ()
    return tuple(value.split(","))
