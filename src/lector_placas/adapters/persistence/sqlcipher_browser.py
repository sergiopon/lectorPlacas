"""Navegador de solo lectura de avistamientos y corridas sobre SQLCipher."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.adapters.persistence.rows import (
    from_db_time,
    row_to_record,
    to_db_time,
)
from lector_placas.application.ports import RunRecord, RunStatus, SightingQuery
from lector_placas.domain.errors import RepositoryError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lector_placas.domain.entities import SightingRecord

MAX_PAGE: Final[int] = 10_000
# SEG-15: consultas literales y constantes; cada filtro se anula con `(? IS NULL OR ...)` y
# los valores van por parámetros. El texto de placa nunca se interpola ni aparece en mensajes.
_SEARCH_SQL: Final[str] = (
    "SELECT sighting_id, run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, "
    "ocr_text, plate_text, confidence, agreement, num_readings, status, reasons, "
    "format_ids, crop_ref, created_at, reviewed_at, plate_width_px, plate_height_px, "
    "sharpness, contrast, duplicate_of FROM sightings "
    "WHERE (? IS NULL OR status = ?) "
    "AND (? IS NULL OR substr(plate_text, 1, length(?)) = ?) "
    "AND (? IS NULL OR run_id = ?) "
    "AND (? IS NULL OR created_at >= ?) "
    "AND (? IS NULL OR created_at < ?) "
    "AND (? = 1 OR duplicate_of IS NULL) "
    "AND (? = 'include' OR (? = 'exclude' AND instr(reasons, 'predicted_') = 0) "
    "OR (? = 'only' AND instr(reasons, 'predicted_') > 0)) "
    "ORDER BY sighting_id DESC LIMIT ? OFFSET ?"
)
_COUNT_SQL: Final[str] = (
    "SELECT count(*) FROM sightings "
    "WHERE (? IS NULL OR status = ?) "
    "AND (? IS NULL OR substr(plate_text, 1, length(?)) = ?) "
    "AND (? IS NULL OR run_id = ?) "
    "AND (? IS NULL OR created_at >= ?) "
    "AND (? IS NULL OR created_at < ?) "
    "AND (? = 1 OR duplicate_of IS NULL) "
    "AND (? = 'include' OR (? = 'exclude' AND instr(reasons, 'predicted_') = 0) "
    "OR (? = 'only' AND instr(reasons, 'predicted_') > 0))"
)
_LIST_RUNS_SQL: Final[str] = (
    "SELECT run_id, profile, status, started_at, finished_at, duration_ms, frames_processed, "
    "sightings_confirmed, sightings_unverified, tracks_without_reading, processing_ms "
    "FROM runs ORDER BY run_id DESC LIMIT ? OFFSET ?"
)
_COUNT_DUPLICATES_SQL: Final[str] = (
    "SELECT duplicate_of, count(*) FROM sightings "
    "WHERE duplicate_of IN (SELECT value FROM json_each(?)) GROUP BY duplicate_of"
)


class SqlCipherSightingBrowser:
    """Navegador de solo lectura que comparte la conexión del repositorio."""

    def __init__(self, connection: sqlcipher.Connection) -> None:
        """Guarda la conexión cifrada abierta por el repositorio.

        Args:
            connection: conexión SQLCipher del repositorio.
        """
        self._connection = connection

    def search_sightings(
        self, query: SightingQuery, limit: int, offset: int
    ) -> list[SightingRecord]:
        """Busca avistamientos combinando los filtros de `query`.

        Args:
            query: filtros a aplicar.
            limit: cantidad máxima de filas (`1 <= limit <= MAX_PAGE`).
            offset: desplazamiento (`>= 0`).

        Returns:
            Avistamientos ordenados por `sighting_id` descendente.

        Raises:
            RepositoryError: si la paginación es inválida o la consulta falla.
        """
        _require_page(limit, offset)
        params = (*_filter_params(query), limit, offset)
        try:
            rows = self._connection.execute(_SEARCH_SQL, params).fetchall()
        except sqlcipher.Error as e:
            raise RepositoryError("search_sightings falló") from e
        return [row_to_record(row) for row in rows]

    def count_sightings(self, query: SightingQuery) -> int:
        """Cuenta los avistamientos que satisfacen `query`.

        Args:
            query: filtros a aplicar.

        Returns:
            Total de filas que devolvería la búsqueda sin paginar.

        Raises:
            RepositoryError: si la consulta falla.
        """
        try:
            row = self._connection.execute(_COUNT_SQL, _filter_params(query)).fetchone()
        except sqlcipher.Error as e:
            raise RepositoryError("count_sightings falló") from e
        return int(row[0])

    def list_runs(self, limit: int, offset: int) -> list[RunRecord]:
        """Lista las corridas registradas de la más reciente a la más antigua.

        Args:
            limit: cantidad máxima de filas (`1 <= limit <= MAX_PAGE`).
            offset: desplazamiento (`>= 0`).

        Returns:
            Corridas ordenadas por `run_id` descendente.

        Raises:
            RepositoryError: si la paginación es inválida o la consulta falla.
        """
        _require_page(limit, offset)
        try:
            rows = self._connection.execute(_LIST_RUNS_SQL, (limit, offset)).fetchall()
        except sqlcipher.Error as e:
            raise RepositoryError("list_runs falló") from e
        return [_row_to_run(row) for row in rows]

    def count_duplicates(self, sighting_ids: Sequence[int]) -> dict[int, int]:
        """Cuenta los duplicados de cada avistamiento de `sighting_ids`.

        Args:
            sighting_ids: identificadores a consultar.

        Returns:
            Número de duplicados por id; los ids sin duplicados no aparecen.

        Raises:
            RepositoryError: si la consulta falla.
        """
        if not sighting_ids:
            return {}
        try:
            rows = self._connection.execute(
                _COUNT_DUPLICATES_SQL, (json.dumps(list(sighting_ids)),)
            ).fetchall()
        except sqlcipher.Error as e:
            raise RepositoryError("count_duplicates falló") from e
        return {int(row[0]): int(row[1]) for row in rows}


def _require_page(limit: int, offset: int) -> None:
    """Valida los parámetros de paginación de una consulta."""
    if not 1 <= limit <= MAX_PAGE or offset < 0:
        raise RepositoryError("parámetros de paginación inválidos")


def _filter_params(query: SightingQuery) -> tuple[object, ...]:
    """Construye los parámetros del WHERE en el orden de las marcas `?`."""
    status = query.status.value if query.status is not None else None
    prefix = query.plate_prefix
    run_id = query.run_id
    from_text = to_db_time(query.created_from) if query.created_from is not None else None
    to_text = to_db_time(query.created_to) if query.created_to is not None else None
    return (
        status,
        status,
        prefix,
        prefix,
        prefix,
        run_id,
        run_id,
        from_text,
        from_text,
        to_text,
        to_text,
        1 if query.include_duplicates else 0,
        query.low_quality,
        query.low_quality,
        query.low_quality,
    )


def _row_to_run(row: tuple[Any, ...]) -> RunRecord:
    """Convierte una fila de `runs` en un `RunRecord`."""
    (
        run_id,
        profile,
        status,
        started_at,
        finished_at,
        duration_ms,
        frames_processed,
        sightings_confirmed,
        sightings_unverified,
        tracks_without_reading,
        processing_ms,
    ) = row
    return RunRecord(
        run_id=run_id,
        profile=profile,
        status=RunStatus(status),
        started_at=from_db_time(started_at),
        finished_at=from_db_time(finished_at) if finished_at is not None else None,
        duration_ms=duration_ms,
        frames_processed=frames_processed,
        sightings_confirmed=sightings_confirmed,
        sightings_unverified=sightings_unverified,
        tracks_without_reading=tracks_without_reading,
        processing_ms=processing_ms,
    )
