"""Adaptador de repositorio de avistamientos sobre una base de datos SQLCipher."""

from __future__ import annotations

import importlib.resources
import os
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.application.ports import AuditEvent, RecordPurge, RunStart, RunStats
from lector_placas.domain.entities import (
    PLATE_TEXT_REGEX,
    ReviewStatus,
    Sighting,
    SightingRecord,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import EncryptionError, RepositoryError, SightingNotFoundError
from lector_placas.infrastructure.crypto import KeyPurpose, derive_key

if TYPE_CHECKING:
    from pathlib import Path

    from lector_placas.application.ports import KeyProvider

SCHEMA_VERSION: Final[int] = 1
MAX_PAGE: Final[int] = 10_000
HEX_KEY_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

_MAX_DETAIL_LEN: Final[int] = 500

_SELECT_SIGHTINGS_PAGE = (
    "SELECT sighting_id, run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, "
    "ocr_text, plate_text, confidence, agreement, num_readings, status, reasons, "
    "format_ids, crop_ref, created_at, reviewed_at FROM sightings "
    "WHERE (? IS NULL OR status = ?) ORDER BY sighting_id LIMIT ? OFFSET ?"
)
_SELECT_SIGHTING_BY_ID = (
    "SELECT sighting_id, run_id, track_id, first_seen_ms, last_seen_ms, vehicle_type, "
    "ocr_text, plate_text, confidence, agreement, num_readings, status, reasons, "
    "format_ids, crop_ref, created_at, reviewed_at FROM sightings WHERE sighting_id = ?"
)

_REVIEWABLE_STATUSES = (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED, ReviewStatus.REJECTED)


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


class SqlCipherPlateRepository:
    """Repositorio de avistamientos respaldado por SQLCipher."""

    def __init__(self, db_path: Path, key_provider: KeyProvider) -> None:
        """Abre (o crea) la base de datos cifrada y aplica el esquema.

        Args:
            db_path: ruta del archivo de base de datos.
            key_provider: proveedor de la clave maestra.

        Raises:
            EncryptionError: si la clave es incorrecta o el archivo está dañado.
            RepositoryError: si la versión del esquema no es soportada.
        """
        self._closed = False
        self._create_if_missing(db_path)
        self._connection = sqlcipher.connect(str(db_path))
        self._apply_key(key_provider)
        self._verify_key()
        self._apply_schema()
        self._check_schema_version()
        db_path.chmod(0o600)

    def _create_if_missing(self, db_path: Path) -> None:
        """Crea el archivo vacío con permisos 0600 si aún no existe."""
        if not db_path.exists():
            fd = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)

    def _apply_key(self, key_provider: KeyProvider) -> None:
        """Deriva la subclave SQLCipher y la aplica a la conexión."""
        key_hex = derive_key(key_provider.master_key(), KeyPurpose.SQLCIPHER).hex()
        if HEX_KEY_REGEX.fullmatch(key_hex) is None:
            raise EncryptionError("la subclave derivada no es hexadecimal válida")
        # SEG-15: única excepción, hex validado
        self._connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")

    def _verify_key(self) -> None:
        """Comprueba que la clave permite leer la base de datos."""
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlcipher.DatabaseError as e:
            self._connection.close()
            raise EncryptionError(
                "no se pudo abrir la base de datos: clave incorrecta o archivo dañado"
            ) from e

    def _apply_schema(self) -> None:
        """Ejecuta el script de esquema empaquetado con el adaptador."""
        schema = (
            importlib.resources.files("lector_placas.adapters.persistence")
            .joinpath("schema.sql")
            .read_text(encoding="utf-8")
        )
        self._connection.executescript(schema)

    def _check_schema_version(self) -> None:
        """Inserta la versión inicial del esquema o valida la existente."""
        with self._connection:
            row = self._connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                )
                version = SCHEMA_VERSION
            else:
                version = row[0]
        if version != SCHEMA_VERSION:
            self._connection.close()
            raise RepositoryError("versión de esquema no soportada")

    def start_run(self, run: RunStart) -> int:
        """Registra el inicio de una corrida de procesamiento.

        Args:
            run: datos de apertura de la corrida.

        Returns:
            Identificador de la corrida creada.

        Raises:
            RepositoryError: si la escritura falla.
        """
        try:
            with self._connection:
                cursor = self._connection.execute(
                    "INSERT INTO runs (video_sha256, profile, width, height, rotation_deg, "
                    "duration_ms, started_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'running')",
                    (
                        run.video_sha256,
                        run.profile,
                        run.video.width,
                        run.video.height,
                        run.video.rotation_deg,
                        run.video.duration_ms,
                        to_db_time(run.started_at),
                    ),
                )
                run_id = cursor.lastrowid
                self._log_event_locked(AuditEvent.RUN_STARTED, run.started_at, f"run_id={run_id}")
        except sqlcipher.Error as e:
            raise RepositoryError("start_run falló") from e
        return int(run_id)

    def finish_run(
        self, run_id: int, stats: RunStats, finished_at: datetime, succeeded: bool
    ) -> None:
        """Cierra una corrida con sus estadísticas finales.

        Args:
            run_id: identificador de la corrida.
            stats: estadísticas agregadas.
            finished_at: fecha de cierre.
            succeeded: si la corrida terminó con éxito.

        Raises:
            RepositoryError: si la corrida no existe o la escritura falla.
        """
        status = "completed" if succeeded else "failed"
        try:
            with self._connection:
                cursor = self._connection.execute(
                    "UPDATE runs SET finished_at = ?, status = ?, frames_decoded = ?, "
                    "frames_processed = ?, tracks_total = ?, sightings_confirmed = ?, "
                    "sightings_unverified = ?, tracks_without_reading = ?, processing_ms = ? "
                    "WHERE run_id = ?",
                    (
                        to_db_time(finished_at),
                        status,
                        stats.frames_decoded,
                        stats.frames_processed,
                        stats.tracks_total,
                        stats.sightings_confirmed,
                        stats.sightings_unverified,
                        stats.tracks_without_reading,
                        stats.processing_ms,
                        run_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise RepositoryError("corrida inexistente")
                self._log_event_locked(
                    AuditEvent.RUN_FINISHED, finished_at, f"run_id={run_id} status={status}"
                )
        except sqlcipher.Error as e:
            raise RepositoryError("finish_run falló") from e

    def save_sighting(self, sighting: Sighting) -> int:
        """Persiste un avistamiento consolidado.

        Args:
            sighting: avistamiento a guardar.

        Returns:
            Identificador del avistamiento creado.

        Raises:
            RepositoryError: si la escritura falla o viola una restricción única.
        """
        plate = sighting.plate
        created_at = to_db_time(sighting.created_at)
        reasons = ",".join(reason.value for reason in plate.reasons)
        format_ids = ",".join(plate.format_ids)
        try:
            with self._connection:
                plate_id = (
                    self._upsert_plate_locked(plate.text, created_at)
                    if plate.status is ReviewStatus.CONFIRMED
                    else None
                )
                cursor = self._connection.execute(
                    "INSERT INTO sightings (run_id, plate_id, track_id, first_seen_ms, "
                    "last_seen_ms, vehicle_type, ocr_text, plate_text, confidence, agreement, "
                    "num_readings, status, reasons, format_ids, crop_ref, created_at, "
                    "reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        sighting.run_id,
                        plate_id,
                        sighting.track_id,
                        sighting.first_seen_ms,
                        sighting.last_seen_ms,
                        sighting.vehicle_type.value,
                        plate.text,
                        plate.text,
                        plate.confidence,
                        plate.agreement,
                        plate.num_readings,
                        plate.status.value,
                        reasons,
                        format_ids,
                        sighting.crop_ref,
                        created_at,
                    ),
                )
                sighting_id = cursor.lastrowid
        except sqlcipher.Error as e:
            raise RepositoryError("save_sighting falló") from e
        return int(sighting_id)

    def _upsert_plate_locked(self, text: str, at: str) -> int:
        """Inserta o actualiza una placa del catálogo y devuelve su id."""
        self._connection.execute(
            "INSERT INTO plates(plate_text, first_seen_at, last_seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT(plate_text) DO UPDATE SET last_seen_at = excluded.last_seen_at",
            (text, at, at),
        )
        row = self._connection.execute(
            "SELECT plate_id FROM plates WHERE plate_text = ?", (text,)
        ).fetchone()
        return int(row[0])

    def list_sightings(
        self, status: ReviewStatus | None, limit: int, offset: int
    ) -> list[SightingRecord]:
        """Lista avistamientos paginados, opcionalmente filtrados por estado.

        Args:
            status: estado a filtrar, o `None` para no filtrar.
            limit: cantidad máxima de filas (`1 <= limit <= MAX_PAGE`).
            offset: desplazamiento (`>= 0`).

        Returns:
            Lista de avistamientos ordenados por `sighting_id`.

        Raises:
            RepositoryError: si `limit` u `offset` son inválidos, o la consulta falla.
        """
        if not 1 <= limit <= MAX_PAGE or offset < 0:
            raise RepositoryError("parámetros de paginación inválidos")
        status_value = status.value if status is not None else None
        try:
            rows = self._connection.execute(
                _SELECT_SIGHTINGS_PAGE,
                (status_value, status_value, limit, offset),
            ).fetchall()
        except sqlcipher.Error as e:
            raise RepositoryError("list_sightings falló") from e
        return [_row_to_record(row) for row in rows]

    def get_sighting(self, sighting_id: int) -> SightingRecord:
        """Obtiene un avistamiento por su identificador.

        Args:
            sighting_id: identificador del avistamiento.

        Returns:
            El avistamiento encontrado.

        Raises:
            SightingNotFoundError: si no existe.
            RepositoryError: si la consulta falla.
        """
        try:
            row = self._connection.execute(
                _SELECT_SIGHTING_BY_ID,
                (sighting_id,),
            ).fetchone()
        except sqlcipher.Error as e:
            raise RepositoryError("get_sighting falló") from e
        if row is None:
            raise SightingNotFoundError(f"sighting_id={sighting_id}")
        return _row_to_record(row)

    def record_review(
        self,
        sighting_id: int,
        status: ReviewStatus,
        corrected_text: str | None,
        reviewed_at: datetime,
    ) -> None:
        """Registra la decisión de revisión humana sobre un avistamiento.

        Args:
            sighting_id: identificador del avistamiento.
            status: nuevo estado (`CONFIRMED`, `CORRECTED` o `REJECTED`).
            corrected_text: texto corregido (solo para `CORRECTED`).
            reviewed_at: fecha de la revisión.

        Raises:
            RepositoryError: si `status` o `corrected_text` son inválidos, o la escritura falla.
            SightingNotFoundError: si el avistamiento no existe.
        """
        self._validate_review_args(status, corrected_text)
        at = to_db_time(reviewed_at)
        try:
            with self._connection:
                self._apply_review_locked(sighting_id, status, corrected_text, at)
        except sqlcipher.Error as e:
            raise RepositoryError("record_review falló") from e

    def _validate_review_args(self, status: ReviewStatus, corrected_text: str | None) -> None:
        """Valida la coherencia entre el estado y el texto corregido."""
        if status not in _REVIEWABLE_STATUSES:
            raise RepositoryError("estado de revisión inválido")
        if status is ReviewStatus.CORRECTED:
            if corrected_text is None or PLATE_TEXT_REGEX.fullmatch(corrected_text) is None:
                raise RepositoryError("corrected_text inválido para CORRECTED")
        elif corrected_text is not None:
            raise RepositoryError("corrected_text solo se admite con CORRECTED")

    def _apply_review_locked(
        self, sighting_id: int, status: ReviewStatus, corrected_text: str | None, at: str
    ) -> None:
        """Aplica la transición de revisión dentro de la transacción activa."""
        current = self._connection.execute(
            "SELECT plate_text FROM sightings WHERE sighting_id = ?", (sighting_id,)
        ).fetchone()
        if current is None:
            raise SightingNotFoundError(f"sighting_id={sighting_id}")
        if status is ReviewStatus.REJECTED:
            cursor = self._connection.execute(
                "UPDATE sightings SET status = ?, plate_id = NULL, reviewed_at = ? "
                "WHERE sighting_id = ?",
                (status.value, at, sighting_id),
            )
        else:
            text = str(current[0])
            if status is ReviewStatus.CORRECTED:
                if corrected_text is None:
                    raise RepositoryError("corrected_text inválido para CORRECTED")
                text = corrected_text
            plate_id = self._upsert_plate_locked(text, at)
            cursor = self._connection.execute(
                "UPDATE sightings SET plate_text = ?, status = ?, plate_id = ?, reviewed_at = ? "
                "WHERE sighting_id = ?",
                (text, status.value, plate_id, at, sighting_id),
            )
        if cursor.rowcount == 0:
            raise SightingNotFoundError(f"sighting_id={sighting_id}")

    def expire_crop_refs(self, cutoff: datetime) -> list[str]:
        """Desvincula los recortes de los avistamientos anteriores a `cutoff`.

        Args:
            cutoff: fecha límite (exclusiva).

        Returns:
            Referencias de recorte desvinculadas, en orden de `sighting_id`.

        Raises:
            RepositoryError: si la escritura falla.
        """
        cutoff_text = to_db_time(cutoff)
        try:
            with self._connection:
                rows = self._connection.execute(
                    "SELECT sighting_id, crop_ref FROM sightings "
                    "WHERE created_at < ? AND crop_ref IS NOT NULL ORDER BY sighting_id",
                    (cutoff_text,),
                ).fetchall()
                refs = [row[1] for row in rows]
                self._connection.execute(
                    "UPDATE sightings SET crop_ref = NULL "
                    "WHERE created_at < ? AND crop_ref IS NOT NULL",
                    (cutoff_text,),
                )
        except sqlcipher.Error as e:
            raise RepositoryError("expire_crop_refs falló") from e
        return refs

    def delete_records_before(self, cutoff: datetime) -> RecordPurge:
        """Purga avistamientos, corridas y placas anteriores a `cutoff`.

        Args:
            cutoff: fecha límite (exclusiva).

        Returns:
            Conteos y referencias de recorte afectados.

        Raises:
            RepositoryError: si la escritura falla.
        """
        cutoff_text = to_db_time(cutoff)
        try:
            with self._connection:
                purge = self._delete_records_before_locked(cutoff_text)
        except sqlcipher.Error as e:
            raise RepositoryError("delete_records_before falló") from e
        return purge

    def _delete_records_before_locked(self, cutoff_text: str) -> RecordPurge:
        """Ejecuta la purga dentro de la transacción activa."""
        rows = self._connection.execute(
            "SELECT sighting_id, crop_ref FROM sightings "
            "WHERE created_at < ? AND crop_ref IS NOT NULL ORDER BY sighting_id",
            (cutoff_text,),
        ).fetchall()
        refs = tuple(row[1] for row in rows)
        sightings_deleted = self._connection.execute(
            "DELETE FROM sightings WHERE created_at < ?", (cutoff_text,)
        ).rowcount
        runs_deleted = self._connection.execute(
            "DELETE FROM runs WHERE started_at < ? "
            "AND run_id NOT IN (SELECT run_id FROM sightings)",
            (cutoff_text,),
        ).rowcount
        plates_deleted = self._connection.execute(
            "DELETE FROM plates WHERE plate_id NOT IN "
            "(SELECT plate_id FROM sightings WHERE plate_id IS NOT NULL)"
        ).rowcount
        return RecordPurge(sightings_deleted, runs_deleted, plates_deleted, refs)

    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None:
        """Registra un evento de auditoría.

        Args:
            event: tipo de evento.
            occurred_at: fecha del evento.
            detail: detalle del evento; nunca debe contener texto de placa.

        Raises:
            RepositoryError: si `detail` supera 500 caracteres o la escritura falla.
        """
        try:
            with self._connection:
                self._log_event_locked(event, occurred_at, detail)
        except sqlcipher.Error as e:
            raise RepositoryError("log_event falló") from e

    def _log_event_locked(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None:
        """Inserta el evento de auditoría dentro de la transacción activa."""
        if len(detail) > _MAX_DETAIL_LEN:
            raise RepositoryError("detail supera la longitud máxima")
        self._connection.execute(
            "INSERT INTO audit_log(event, occurred_at, detail) VALUES (?, ?, ?)",
            (event.value, to_db_time(occurred_at), detail),
        )

    def close(self) -> None:
        """Cierra la conexión a la base de datos, de forma idempotente."""
        if not self._closed:
            self._connection.close()
            self._closed = True


def _row_to_record(row: tuple[Any, ...]) -> SightingRecord:
    """Convierte una fila de `sightings` en un `SightingRecord`."""
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
