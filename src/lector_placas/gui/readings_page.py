"""Página "Lecturas": galería de placas con panel de revisión (spec 048, ADR-015)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ImageBGR, ReviewDecision, SightingQuery
from lector_placas.application.review_sightings import DecideSighting
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import (
    CropNotFoundError,
    CropStoreError,
    EncryptionError,
    RepositoryError,
    ReviewError,
    SightingNotFoundError,
)
from lector_placas.gui.card_grid import CardGrid
from lector_placas.gui.images import bgr_to_pixmap
from lector_placas.gui.plate_card import CROP_BOX
from lector_placas.gui.readings_filters import FILTER_ORDER, ReadingsFilters
from lector_placas.gui.review_panel import ReviewPanel
from lector_placas.gui.session import GuiSession

PAGE_SIZE: Final[int] = 60
RUNS_LIMIT: Final[int] = 50
DIALOG_TITLE: Final[str] = "lectorPlacas"
PURGED_NOTE: Final[str] = "La imagen ya se borró por antigüedad."
UNREADABLE_NOTE: Final[str] = "No se pudo abrir la imagen."


class ReadingsPage(QWidget):
    """Galería de placas con filtros, panel de revisión y atajos de decisión."""

    pending_changed = Signal(int)

    _session: GuiSession
    _filters: ReadingsFilters
    _grid: CardGrid
    _more_button: QPushButton
    _panel: ReviewPanel
    _records: dict[int, SightingRecord]
    _total: int
    _total_all: int
    _pending: int

    def __init__(self, session: GuiSession) -> None:
        """Construye la página con el filtro inicial y la primera página cargada."""
        super().__init__()
        self._session = session
        self._records = {}
        self._total = 0
        self._total_all = 0
        self._pending = 0
        _build_page(self)
        try:
            pending = _global_pending(self)
        except RepositoryError:
            pending = 0
        self._filters.set_status(ReviewStatus.UNVERIFIED if pending > 0 else None)
        self.reload()

    def reload(self) -> None:
        """Recuenta los filtros, emite los pendientes y carga la primera página."""
        try:
            runs = self._session.browser.list_runs(RUNS_LIMIT, 0)
            counts = _status_counts(self)
            pending = _global_pending(self)
            total_all = self._session.browser.count_sightings(SightingQuery())
        except RepositoryError as error:
            _show_error(self, str(error))
            return
        self._filters.set_runs(runs)
        self._filters.set_counts(counts)
        self._total_all = total_all
        self._pending = pending
        self.pending_changed.emit(pending)
        _load_page(self, append=False)

    def show_run(self, run_id: int | None, status: ReviewStatus | None) -> None:
        """Fija video y estado en los filtros y recarga, seleccionando la primera tarjeta."""
        self._filters.set_run_id(run_id)
        self._filters.set_status(status)
        self.reload()
        ids = self._grid.ids()
        if ids:
            self._grid.select(ids[0])

    def set_busy(self, busy: bool) -> None:
        """Bloquea las decisiones mientras hay un procesamiento en curso (ARQUITECTURA §7)."""
        self._panel.set_actions_enabled(not busy)

    def pending_count(self) -> int:
        """Devuelve el último total global de placas por revisar."""
        return self._pending

    def _on_skip(self) -> None:
        current = self._grid.selected_id()
        if current is not None:
            _select_next(self, self._grid.next_id(current))


def _build_page(page: ReadingsPage) -> None:
    page._filters = ReadingsFilters(page)
    page._filters.changed.connect(page.reload)
    page._grid = CardGrid(page)
    page._grid.selection_changed.connect(lambda sighting_id: _on_selection(page, sighting_id))
    page._more_button = QPushButton("Mostrar más", page)
    page._more_button.clicked.connect(lambda: _load_page(page, append=True))
    page._more_button.setVisible(False)
    page._panel = ReviewPanel(page)
    page._panel.decided.connect(lambda decision: _on_decided(page, decision))
    page._panel.skip_requested.connect(page._on_skip)
    _arrange(page)
    _build_shortcuts(page)


def _arrange(page: ReadingsPage) -> None:
    left = QWidget(page)
    left_layout = QVBoxLayout(left)
    left_layout.addWidget(page._grid, 1)
    left_layout.addWidget(page._more_button)
    splitter = QSplitter(Qt.Orientation.Horizontal, page)
    splitter.addWidget(left)
    splitter.addWidget(page._panel)
    title = QLabel("Lecturas", page)
    title.setProperty("role", "title")
    layout = QVBoxLayout(page)
    layout.addWidget(title)
    layout.addWidget(page._filters)
    layout.addWidget(splitter, 1)


def _build_shortcuts(page: ReadingsPage) -> None:
    panel = page._panel
    triggers = (
        ("C", panel.confirm),
        ("E", panel.start_edit),
        ("R", panel.reject),
        ("B", panel.mark_illegible),
        ("S", panel.skip),
    )
    for key, trigger in triggers:
        shortcut = QShortcut(QKeySequence(key), page)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(trigger)


def _query(page: ReadingsPage) -> SightingQuery:
    return SightingQuery(
        status=page._filters.status(),
        plate_prefix=page._filters.plate_prefix(),
        run_id=page._filters.run_id(),
    )


def _status_counts(page: ReadingsPage) -> dict[ReviewStatus | None, int]:
    prefix, run_id = page._filters.plate_prefix(), page._filters.run_id()
    return {
        status: page._session.browser.count_sightings(
            SightingQuery(status=status, plate_prefix=prefix, run_id=run_id)
        )
        for status in FILTER_ORDER
    }


def _global_pending(page: ReadingsPage) -> int:
    return page._session.browser.count_sightings(SightingQuery(status=ReviewStatus.UNVERIFIED))


def _load_page(page: ReadingsPage, *, append: bool) -> None:
    query = _query(page)
    offset = len(page._records) if append else 0
    try:
        records = page._session.browser.search_sightings(query, PAGE_SIZE, offset)
        total = page._session.browser.count_sightings(query)
    except RepositoryError as error:
        _show_error(page, str(error))
        return
    if not append:
        page._records = {}
        page._panel.clear()
    page._records.update({record.sighting_id: record for record in records})
    crops = _load_crops(page, records)
    if append:
        page._grid.append_records(records, crops)
    else:
        page._grid.set_records(records, crops)
        page._grid.select(None)
    page._total = total
    page._more_button.setVisible(len(page._records) < total)
    _set_empty_message(page)


def _load_crops(page: ReadingsPage, records: list[SightingRecord]) -> dict[int, QPixmap | None]:
    crops: dict[int, QPixmap | None] = {}
    for record in records:
        image, _note = _load_crop(page, record)
        crops[record.sighting_id] = None if image is None else bgr_to_pixmap(image, *CROP_BOX)
    return crops


def _load_crop(page: ReadingsPage, record: SightingRecord) -> tuple[ImageBGR | None, str | None]:
    if record.crop_ref is None:
        return None, None
    try:
        return page._session.crop_store.load(record.crop_ref), None
    except CropNotFoundError:
        return None, PURGED_NOTE
    except (CropStoreError, EncryptionError):
        return None, UNREADABLE_NOTE


def _set_empty_message(page: ReadingsPage) -> None:
    if page._total_all == 0:
        page._grid.set_empty_message(
            "Aún no hay lecturas", "Procesa un video para ver aquí las placas encontradas."
        )
        return
    pending_filter = (
        page._filters.status() is ReviewStatus.UNVERIFIED and page._filters.plate_prefix() is None
    )
    if page._total == 0 and pending_filter:
        page._grid.set_empty_message("¡Todo revisado!", "No quedan placas pendientes.")
        return
    page._grid.set_empty_message("Sin resultados", "Prueba con otra placa o quita los filtros.")


def _show_error(page: ReadingsPage, message: str) -> None:
    page._records = {}
    page._grid.set_records([], {})
    page._grid.set_empty_message("No se pudieron cargar las lecturas", message)
    page._more_button.setVisible(False)
    page._panel.clear()


def _on_selection(page: ReadingsPage, sighting_id: int) -> None:
    record = page._records.get(sighting_id)
    if record is None:
        page._panel.clear()
        return
    crop, note = _load_crop(page, record)
    page._panel.show_record(record, crop, note)


def _on_decided(page: ReadingsPage, decision: object) -> None:
    current = page._grid.selected_id()
    if current is None or not isinstance(decision, ReviewDecision):
        return
    next_id = page._grid.next_id(current)
    try:
        updated = DecideSighting(page._session.repository, page._session.clock).execute(
            current, decision
        )
    except (ReviewError, SightingNotFoundError, RepositoryError) as error:
        QMessageBox.warning(page, DIALOG_TITLE, str(error))
        return
    _apply_decision(page, current, updated)
    _refresh_counts(page)
    _select_next(page, next_id)


def _apply_decision(page: ReadingsPage, current: int, updated: SightingRecord) -> None:
    if page._filters.status() in (None, updated.status):
        page._records[current] = updated
        page._grid.update_record(updated)
        return
    page._records.pop(current, None)
    page._grid.remove(current)


def _refresh_counts(page: ReadingsPage) -> None:
    try:
        counts = _status_counts(page)
        pending = _global_pending(page)
    except RepositoryError as error:
        _show_error(page, str(error))
        return
    page._filters.set_counts(counts)
    page._pending = pending
    page.pending_changed.emit(pending)


def _select_next(page: ReadingsPage, next_id: int | None) -> None:
    if next_id is None:
        page._panel.clear()
        return
    page._grid.select(next_id)
