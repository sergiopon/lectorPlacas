"""Caso de uso de purga por retención (SEG-03, ADR-005)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from lector_placas.application.ports import (
    AuditEvent,
    Clock,
    CropStore,
    ExportStore,
    PlateRepository,
)
from lector_placas.domain.errors import ConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Días de retención de recortes y de registros."""

    crops_days: int
    records_days: int

    def __post_init__(self) -> None:
        """Valida la relación entre los días de retención.

        Raises:
            ConfigurationError: si no se cumple `1 <= crops_days <= records_days`.
        """
        if not 1 <= self.crops_days <= self.records_days:
            raise ConfigurationError(
                f"retención inválida: crops_days={self.crops_days} records_days={self.records_days}"
            )


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """Conteos de lo borrado por una purga por retención."""

    crops_deleted: int
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    exports_deleted: int


class PurgeExpiredData:
    """Borra los datos vencidos según la política de retención.

    Borra los registros anteriores a `records_days` (avistamientos, corridas y placas),
    desvincula y borra los recortes anteriores a `crops_days` (incluidos los huérfanos) y
    borra las exportaciones vencidas, dejando constancia en el registro de auditoría.
    """

    def __init__(
        self,
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        policy: RetentionPolicy,
    ) -> None:
        """Inicializa el caso de uso con sus puertos y su política.

        Args:
            repository: repositorio que borra registros y desvincula recortes.
            crop_store: almacén de recortes de placa cifrados.
            export_store: almacén de exportaciones de avistamientos.
            clock: fuente de la hora actual en UTC.
            policy: días de retención de recortes y de registros.
        """
        self._repository = repository
        self._crop_store = crop_store
        self._export_store = export_store
        self._clock = clock
        self._policy = policy

    def execute(self) -> PurgeResult:
        """Ejecuta la purga en orden y registra el evento de auditoría.

        Returns:
            Conteos de recortes, avistamientos, corridas, placas y exportaciones borrados.
        """
        now = self._clock.now()
        records_cutoff = now - timedelta(days=self._policy.records_days)
        crops_cutoff = now - timedelta(days=self._policy.crops_days)
        purge = self._repository.delete_records_before(records_cutoff)
        expired = self._repository.expire_crop_refs(crops_cutoff)
        refs = sorted(set(purge.crop_refs) | set(expired))
        for ref in refs:
            self._crop_store.delete(ref)
        swept = self._crop_store.delete_older_than(crops_cutoff)
        exports = self._export_store.delete_older_than(records_cutoff)
        result = PurgeResult(
            crops_deleted=len(refs) + swept,
            sightings_deleted=purge.sightings_deleted,
            runs_deleted=purge.runs_deleted,
            plates_deleted=purge.plates_deleted,
            exports_deleted=exports,
        )
        detail = (
            f"recortes={result.crops_deleted} avistamientos={result.sightings_deleted}"
            f" corridas={result.runs_deleted} placas={result.plates_deleted}"
            f" exportaciones={result.exports_deleted}"
        )
        self._repository.log_event(AuditEvent.PURGE, now, detail)
        logger.info("purga completada %s", detail)
        return result
