"""Caso de uso: exportar los avistamientos paginados a un archivo CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from lector_placas.application.ports import (
    AuditEvent,
    Clock,
    ExportStore,
    PlateRepository,
)
from lector_placas.domain.entities import ReviewStatus, SightingRecord

PAGE_SIZE: Final[int] = 500


class ExportSightings:
    """Exporta los avistamientos del repositorio y audita la exportación."""

    def __init__(
        self, repository: PlateRepository, export_store: ExportStore, clock: Clock
    ) -> None:
        """Crea el caso de uso con sus dependencias.

        Args:
            repository: repositorio de avistamientos y auditoría.
            export_store: almacén donde se escriben las exportaciones.
            clock: fuente de la hora actual (UTC).
        """
        self._repository = repository
        self._export_store = export_store
        self._clock = clock

    def execute(self, status: ReviewStatus | None) -> Path:
        """Exporta los avistamientos con el estado indicado (o todos) a un CSV.

        Args:
            status: estado por el que filtrar; `None` exporta todos los avistamientos.

        Returns:
            Ruta del archivo CSV escrito.

        Raises:
            ExportError: Si falla la escritura de la exportación.
            RepositoryError: Si falla la lectura de los avistamientos o la auditoría.
        """
        now = self._clock.now()
        records = self._collect(status)
        path = self._export_store.write_sightings(records, now)
        detail = f"filas={len(records)} archivo={path.name}"
        self._repository.log_event(AuditEvent.EXPORT, now, detail)
        return path

    def _collect(self, status: ReviewStatus | None) -> list[SightingRecord]:
        """Recorre todas las páginas de avistamientos con el filtro indicado."""
        records: list[SightingRecord] = []
        offset = 0
        while True:
            page = self._repository.list_sightings(status, PAGE_SIZE, offset)
            records.extend(page)
            if len(page) < PAGE_SIZE:
                return records
            offset += PAGE_SIZE
