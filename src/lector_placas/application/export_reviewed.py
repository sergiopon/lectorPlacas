"""Caso de uso: exportar los recortes revisados para reentrenar el OCR (spec 035)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lector_placas.application.ports import (
    AuditEvent,
    Clock,
    CropStore,
    ImageBGR,
    PlateRepository,
    TrainingExportStore,
)
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import CropNotFoundError

logger = logging.getLogger(__name__)

PAGE_SIZE: Final[int] = 500
EXPORTED_STATUSES: Final[tuple[ReviewStatus, ...]] = (
    ReviewStatus.CONFIRMED,
    ReviewStatus.CORRECTED,
)


@dataclass(frozen=True, slots=True)
class ExportReviewedResult:
    """Resultado de una exportación de recortes revisados."""

    path: Path
    exported: int
    skipped: int


class ExportReviewedCrops:
    """Exporta los recortes de los avistamientos confirmados y corregidos.

    Solo se exportan los avistamientos con estado `confirmed` o `corrected` que aún
    conservan su recorte; los demás se cuentan como omitidos.
    """

    def __init__(
        self,
        repository: PlateRepository,
        crop_store: CropStore,
        training_store: TrainingExportStore,
        clock: Clock,
    ) -> None:
        """Crea el caso de uso con sus dependencias.

        Args:
            repository: repositorio de avistamientos y auditoría.
            crop_store: almacén de recortes de placa cifrados.
            training_store: almacén donde se escriben las muestras de entrenamiento.
            clock: fuente de la hora actual (UTC).
        """
        self._repository = repository
        self._crop_store = crop_store
        self._training_store = training_store
        self._clock = clock

    def execute(self) -> ExportReviewedResult:
        """Exporta los recortes revisados y audita la exportación.

        Returns:
            La ruta del conjunto escrito, cuántas muestras se exportaron y cuántas se omitieron.

        Raises:
            ExportError: Si falla la escritura de las muestras.
            RepositoryError: Si falla la lectura de los avistamientos o la auditoría.
        """
        now = self._clock.now()
        samples, skipped = self._collect()
        path = self._training_store.write_samples(samples, now)
        detail = f"entrenamiento filas={len(samples)} omitidos={skipped} carpeta={path.name}"
        self._repository.log_event(AuditEvent.EXPORT, now, detail)
        logger.info("exportación de entrenamiento %s", detail)
        return ExportReviewedResult(path, len(samples), skipped)

    def _collect(self) -> tuple[list[tuple[str, ImageBGR]], int]:
        """Recorre los estados exportables y reúne sus muestras disponibles."""
        samples: list[tuple[str, ImageBGR]] = []
        skipped = 0
        for status in EXPORTED_STATUSES:
            for record in self._list_all(status):
                image = self._load_crop(record)
                if image is None:
                    skipped += 1
                else:
                    samples.append((record.plate_text, image))
        return samples, skipped

    def _list_all(self, status: ReviewStatus) -> list[SightingRecord]:
        """Recorre todas las páginas de avistamientos con el estado indicado."""
        records: list[SightingRecord] = []
        offset = 0
        while True:
            page = self._repository.list_sightings(status, PAGE_SIZE, offset)
            records.extend(page)
            if len(page) < PAGE_SIZE:
                return records
            offset += PAGE_SIZE

    def _load_crop(self, record: SightingRecord) -> ImageBGR | None:
        """Carga el recorte del registro, o `None` si no está disponible."""
        if record.crop_ref is None:
            return None
        try:
            return self._crop_store.load(record.crop_ref)
        except CropNotFoundError:
            return None
