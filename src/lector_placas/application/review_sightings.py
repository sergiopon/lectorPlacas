"""Caso de uso de revisión humana de los avistamientos sin verificar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

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
AUDIT_PAGE_SIZE: Final[int] = 500
REVIEWABLE_STATUSES: Final[frozenset[ReviewStatus]] = frozenset(
    {ReviewStatus.UNVERIFIED, ReviewStatus.CONFIRMED}
)
APPLICABLE_ACTIONS: Final[dict[ReviewAction, ReviewStatus]] = {
    ReviewAction.CONFIRM: ReviewStatus.CONFIRMED,
    ReviewAction.CORRECT: ReviewStatus.CORRECTED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
}


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
        return _detail(self.confirmed, self.corrected, self.rejected, self.skipped)


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

    def execute(self, limit: int, status: ReviewStatus = ReviewStatus.UNVERIFIED) -> ReviewSummary:
        """Revisa hasta `limit` avistamientos del estado indicado.

        Con `unverified` revisa los pendientes sin verificar; con `confirmed` audita los
        avistamientos ya confirmados que todavía no ha visto un humano.

        Args:
            limit: número máximo de avistamientos a revisar, entre 1 y 10000.
            status: estado a revisar, dentro de `REVIEWABLE_STATUSES`.

        Returns:
            Resumen con el conteo de cada tipo de decisión.

        Raises:
            ReviewError: si `limit` está fuera del rango admitido o el estado no es revisable.
        """
        _require_limit(limit)
        _require_reviewable(status)
        records = self._select(limit, status)
        counters = _Counters()
        try:
            for record in records:
                if not self._review(record, counters):
                    break
        finally:
            self._ui.close()
        self._repository.log_event(AuditEvent.REVIEW, self._clock.now(), counters.detail())
        return counters.summary()

    def _select(self, limit: int, status: ReviewStatus) -> list[SightingRecord]:
        """Recupera los avistamientos a revisar según el estado pedido."""
        if status is ReviewStatus.UNVERIFIED:
            return self._repository.list_sightings(status, limit, 0)
        return self._unreviewed_confirmed(limit)

    def _unreviewed_confirmed(self, limit: int) -> list[SightingRecord]:
        """Audita los confirmados sin revisar, paginando hasta reunir `limit`."""
        pending: list[SightingRecord] = []
        offset = 0
        while len(pending) < limit:
            page = self._repository.list_sightings(ReviewStatus.CONFIRMED, AUDIT_PAGE_SIZE, offset)
            pending.extend(record for record in page if record.reviewed_at is None)
            if len(page) < AUDIT_PAGE_SIZE:
                break
            offset += AUDIT_PAGE_SIZE
        return pending[:limit]

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


class DecideSighting:
    """Aplica una sola decisión del operador a un avistamiento concreto."""

    def __init__(self, repository: PlateRepository, clock: Clock) -> None:
        """Crea el caso de uso con sus dependencias.

        Args:
            repository: repositorio de avistamientos y auditoría.
            clock: fuente de la hora actual en UTC.
        """
        self._repository = repository
        self._clock = clock

    def execute(self, sighting_id: int, decision: ReviewDecision) -> SightingRecord:
        """Registra una decisión sobre un solo avistamiento.

        Vale cualquier acción aplicable (`CONFIRM`, `CORRECT`, `REJECT`) sobre un avistamiento
        en cualquier estado; el operador puede cambiar de opinión. `ocr_text` nunca cambia.

        Args:
            sighting_id: identificador del avistamiento a decidir.
            decision: acción del operador y, si procede, el texto corregido.

        Returns:
            El registro del avistamiento ya actualizado.

        Raises:
            ReviewError: si la acción no es aplicable a un avistamiento (`SKIP` o `QUIT`).
            SightingNotFoundError: si no existe el avistamiento indicado.
            RepositoryError: si el repositorio rechaza la operación.
        """
        status = APPLICABLE_ACTIONS.get(decision.action)
        if status is None:
            raise ReviewError(f"acción no aplicable a un avistamiento: {decision.action.value}")
        reviewed_at = self._clock.now()
        corrected_text = decision.corrected_text if status is ReviewStatus.CORRECTED else None
        self._repository.record_review(sighting_id, status, corrected_text, reviewed_at)
        self._repository.log_event(
            AuditEvent.REVIEW, self._clock.now(), _action_detail(decision.action)
        )
        return self._repository.get_sighting(sighting_id)


def _detail(confirmed: int, corrected: int, rejected: int, skipped: int) -> str:
    """Compone el detalle de auditoría de una revisión, sin texto de placa."""
    return (
        f"confirmados={confirmed} corregidos={corrected} rechazados={rejected} omitidos={skipped}"
    )


def _action_detail(action: ReviewAction) -> str:
    """Compone el detalle de auditoría de una única decisión aplicada."""
    return _detail(
        int(action is ReviewAction.CONFIRM),
        int(action is ReviewAction.CORRECT),
        int(action is ReviewAction.REJECT),
        0,
    )


def _require_limit(limit: int) -> None:
    """Exige un límite dentro del rango admitido."""
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise ReviewError(f"limit fuera de [{MIN_LIMIT}, {MAX_LIMIT}]: {limit}")


def _require_reviewable(status: ReviewStatus) -> None:
    """Exige un estado susceptible de revisión humana."""
    if status not in REVIEWABLE_STATUSES:
        raise ReviewError(f"estado no revisable: {status.value}")
