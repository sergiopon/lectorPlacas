"""Caso de uso: exportar el dataset de legibilidad (SEG-07)."""

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
    LegibilityExportStore,
    LegibilityLabel,
    LegibilitySample,
    PlateRepository,
)
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import CropNotFoundError, ExportError

logger = logging.getLogger(__name__)

PAGE_SIZE: Final[int] = 500
LABELS: Final[dict[ReviewStatus, LegibilityLabel]] = {
    ReviewStatus.CONFIRMED: LegibilityLabel.LEGIBLE,
    ReviewStatus.CORRECTED: LegibilityLabel.LEGIBLE,
    ReviewStatus.ILLEGIBLE: LegibilityLabel.BLURRY,
    ReviewStatus.REJECTED: LegibilityLabel.NOT_PLATE,
}


@dataclass(frozen=True, slots=True)
class ExportLegibilityResult:
    """Resultado de una exportación del dataset de legibilidad."""

    path: Path
    exported: int
    skipped: int
    per_label: dict[LegibilityLabel, int]


class ExportLegibilityDataset:
    """Exporta los recortes de todos los avistamientos con estado final.

    Recorre los estados `confirmed`, `corrected`, `illegible` y `rejected` —nunca
    `unverified`— y escribe una muestra por avistamiento con su recorte, su clase de
    legibilidad y las métricas del consolidador. Las corridas del mismo video comparten
    un grupo, de modo que el filtro de proximidad puede repartir por video sin exponer su hash.
    """

    def __init__(
        self,
        repository: PlateRepository,
        crop_store: CropStore,
        legibility_store: LegibilityExportStore,
        clock: Clock,
    ) -> None:
        """Crea el caso de uso con sus dependencias.

        Args:
            repository: repositorio de avistamientos y auditoría.
            crop_store: almacén de recortes de placa cifrados.
            legibility_store: almacén donde se escriben las muestras etiquetadas.
            clock: fuente de la hora actual (UTC).
        """
        self._repository = repository
        self._crop_store = crop_store
        self._legibility_store = legibility_store
        self._clock = clock

    def execute(self) -> ExportLegibilityResult:
        """Exporta el dataset de legibilidad y audita la exportación.

        Returns:
            La ruta del conjunto escrito, cuántas muestras se exportaron, cuántas se
            omitieron y el conteo por clase.

        Raises:
            ExportError: Si un avistamiento pertenece a una corrida sin video o falla la
                escritura de las muestras.
            RepositoryError: Si falla la lectura de los avistamientos o la auditoría.
        """
        now = self._clock.now()
        groups = _video_groups(self._repository.run_video_hashes())
        sizes = self._repository.run_frame_sizes()
        samples, skipped, per_label = self._collect(groups, sizes)
        path = self._legibility_store.write_samples(samples, now)
        detail = _detail(samples, skipped, per_label, path)
        self._repository.log_event(AuditEvent.EXPORT, now, detail)
        logger.info("exportación de legibilidad %s", detail)
        return ExportLegibilityResult(path, len(samples), skipped, per_label)

    def _collect(
        self, groups: dict[int, int], sizes: dict[int, tuple[int, int]]
    ) -> tuple[list[LegibilitySample], int, dict[LegibilityLabel, int]]:
        """Recorre los estados exportables y reúne sus muestras disponibles."""
        samples: list[LegibilitySample] = []
        skipped = 0
        per_label: dict[LegibilityLabel, int] = {label: 0 for label in LegibilityLabel}
        for status, label in LABELS.items():
            for record in self._list_all(status):
                image = self._load_crop(record)
                if image is None:
                    skipped += 1
                    continue
                samples.append(self._sample(record, label, image, groups, sizes))
                per_label[label] += 1
        return samples, skipped, per_label

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

    def _sample(
        self,
        record: SightingRecord,
        label: LegibilityLabel,
        image: ImageBGR,
        groups: dict[int, int],
        sizes: dict[int, tuple[int, int]],
    ) -> LegibilitySample:
        """Construye la muestra de un registro con recorte disponible.

        Raises:
            ExportError: Si la corrida del registro no está registrada como video.
        """
        if record.run_id not in groups:
            raise ExportError("corrida sin video")
        frame_width, frame_height = sizes.get(record.run_id, (None, None))
        return LegibilitySample(
            image=image,
            label=label,
            status=record.status,
            human_reviewed=record.reviewed_at is not None,
            video_group=groups[record.run_id],
            run_id=record.run_id,
            track_id=record.track_id,
            vehicle_type=record.vehicle_type,
            confidence=record.confidence,
            agreement=record.agreement,
            num_readings=record.num_readings,
            reasons=record.reasons,
            plate_width_px=record.quality.plate_width_px if record.quality is not None else None,
            plate_height_px=record.quality.plate_height_px if record.quality is not None else None,
            sharpness=record.quality.sharpness if record.quality is not None else None,
            contrast=record.quality.contrast if record.quality is not None else None,
            frame_width=frame_width,
            frame_height=frame_height,
        )


def _video_groups(hashes: dict[int, str]) -> dict[int, int]:
    """Numera los videos distintos según el menor `run_id` que los usa.

    Args:
        hashes: `run_id` → hash del video de todas las corridas.

    Returns:
        `run_id` → número de grupo (1, 2, 3…), compartido por las corridas del mismo video.
    """
    groups: dict[int, int] = {}
    numbers: dict[str, int] = {}
    for run_id in sorted(hashes):
        digest = hashes[run_id]
        if digest not in numbers:
            numbers[digest] = len(numbers) + 1
        groups[run_id] = numbers[digest]
    return groups


def _detail(
    samples: list[LegibilitySample],
    skipped: int,
    per_label: dict[LegibilityLabel, int],
    path: Path,
) -> str:
    """Compone el detalle de auditoría, sin texto de placa ni hash de video (SEG-05)."""
    return (
        f"legibilidad filas={len(samples)} omitidos={skipped}"
        f" legibles={per_label[LegibilityLabel.LEGIBLE]}"
        f" borrosas={per_label[LegibilityLabel.BLURRY]}"
        f" no_placa={per_label[LegibilityLabel.NOT_PLATE]} carpeta={path.name}"
    )
