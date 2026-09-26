"""Caso de uso de revisión humana de los avistamientos sin verificar."""

from __future__ import annotations

from dataclasses import dataclass

from lector_placas.application.ports import (
    AuditEvent,
    Clock,
    CropStore,
    ImageBGR,
    PlateRepository,
    ReviewAction,
    ReviewDecision,
    ReviewUI,
)
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import CropNotFoundError, ReviewError

MIN_LIMIT = 1
MAX_LIMIT = 10000


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Conteo de las decisiones tomadas durante una sesión de revisión."""

    confirmed: int
    corrected: int
    rejected: int
    skipped: int


@dataclass(slots=True)
class _Counters:
    """Acumulador mutable de las decisiones de la sesión."""

    confirmed: int = 0
    corrected: int = 0
    rejected: int = 0
    skipped: int = 0

    def summary(self) -> ReviewSummary:
        """Devuelve el resumen inmutable con los conteos acumulados."""
        return ReviewSummary(self.confirmed, self.corrected, self.rejected, self.skipped)

    def detail(self) -> str:
        """Compone el detalle de auditoría, sin texto de placa."""
        return (
            f"confirmados={self.confirmed} corregidos={self.corrected} "
            f"rechazados={self.rejected} omitidos={self.skipped}"
        )


class ReviewSightings:
    """Recorre los avistamientos sin verificar y registra la decisión del operador."""

    def __init__(
        self,
        repository: PlateRepository,
        crop_store: CropStore,
        ui: ReviewUI,
        clock: Clock,
    ) -> None:
        """Crea el caso de uso con sus dependencias.

        Args:
            repository: repositorio de avistamientos y auditoría.
            crop_store: almacén de recortes cifrados.
            ui: interfaz que presenta cada avistamiento al operador.
            clock: fuente de la hora actual en UTC.
        """
        self._repository = repository
        self._crop_store = crop_store
        self._ui = ui
        self._clock = clock

    def execute(self, limit: int) -> ReviewSummary:
        """Revisa hasta `limit` avistamientos en estado `unverified`.

        Args:
            limit: número máximo de avistamientos a revisar, entre 1 y 10000.

        Returns:
            Resumen con el conteo de cada tipo de decisión.

        Raises:
            ReviewError: si `limit` está fuera del rango admitido.
        """
        _require_limit(limit)
        records = self._repository.list_sightings(ReviewStatus.UNVERIFIED, limit, 0)
        counters = _Counters()
        try:
            for record in records:
                if not self._review(record, counters):
                    break
        finally:
            self._ui.close()
        self._repository.log_event(AuditEvent.REVIEW, self._clock.now(), counters.detail())
        return counters.summary()

    def _review(self, record: SightingRecord, counters: _Counters) -> bool:
        """Pide y aplica la decisión de un avistamiento; `False` si el operador sale."""
        decision = self._ui.ask(record, self._load_crop(record.crop_ref))
        self._apply(record.sighting_id, decision, counters)
        return decision.action is not ReviewAction.QUIT

    def _load_crop(self, crop_ref: str | None) -> ImageBGR | None:
        """Carga el recorte indicado, o `None` si no hay referencia o falta el archivo."""
        if crop_ref is None:
            return None
        try:
            return self._crop_store.load(crop_ref)
        except CropNotFoundError:
            return None

    def _apply(self, sighting_id: int, decision: ReviewDecision, counters: _Counters) -> None:
        """Persiste la decisión en el repositorio y actualiza los conteos."""
        action = decision.action
        reviewed_at = self._clock.now()
        if action is ReviewAction.CONFIRM:
            self._repository.record_review(sighting_id, ReviewStatus.CONFIRMED, None, reviewed_at)
            counters.confirmed += 1
        elif action is ReviewAction.CORRECT:
            self._repository.record_review(
                sighting_id, ReviewStatus.CORRECTED, decision.corrected_text, reviewed_at
            )
            counters.corrected += 1
        elif action is ReviewAction.REJECT:
            self._repository.record_review(sighting_id, ReviewStatus.REJECTED, None, reviewed_at)
            counters.rejected += 1
        elif action is ReviewAction.SKIP:
            counters.skipped += 1


def _require_limit(limit: int) -> None:
    """Exige un límite dentro del rango admitido."""
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise ReviewError(f"limit fuera de [{MIN_LIMIT}, {MAX_LIMIT}]: {limit}")
