"""Pestaña "Avistamientos": composición de filtros, tabla, detalle y revisión (ADR-015)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QModelIndex, QPersistentModelIndex
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import SightingQuery
from lector_placas.application.review_sightings import ReviewSightings, ReviewSummary
from lector_placas.domain.entities import ReviewStatus
from lector_placas.domain.errors import (
    CropStoreError,
    EncryptionError,
    InvalidEntityError,
    RepositoryError,
    ReviewError,
)
from lector_placas.gui.review_dialog import QtReviewUI
from lector_placas.gui.session import GuiSession
from lector_placas.gui.sightings_detail import SightingsDetail
from lector_placas.gui.sightings_filters import SightingsFilters
from lector_placas.gui.sightings_model import SIGHTING_COLUMNS, SightingsTableModel
from lector_placas.gui.widgets import NoCopyTableView

__all__ = ["PAGE_SIZE", "SIGHTING_COLUMNS", "SightingsTab", "SightingsTableModel"]

PAGE_SIZE: Final[int] = 100
DIALOG_TITLE: Final[str] = "lectorPlacas"
INVALID_RANGE_MESSAGE: Final[str] = "rango de fechas inválido"
PAGE_LABEL_EMPTY: Final[str] = "sin resultados"
DEFAULT_REVIEW_LIMIT: Final[int] = 50
MIN_REVIEW_LIMIT: Final[int] = 1
MAX_REVIEW_LIMIT: Final[int] = 10000


def _summary_text(summary: ReviewSummary) -> str:
    """Compone el resumen de una sesión de revisión, sin texto de placa."""
    return (
        f"confirmados={summary.confirmed} corregidos={summary.corrected} "
        f"rechazados={summary.rejected} omitidos={summary.skipped}"
    )


def _build_pagination(tab: SightingsTab) -> QHBoxLayout:
    """Crea los botones de paginación y la etiqueta de página de `tab`."""
    tab._prev_button = QPushButton("Anterior", tab)
    tab._next_button = QPushButton("Siguiente", tab)
    tab._page_label = QLabel(tab)
    tab._prev_button.clicked.connect(tab._on_previous_clicked)
    tab._next_button.clicked.connect(tab._on_next_clicked)
    layout = QHBoxLayout()
    layout.addWidget(tab._prev_button)
    layout.addWidget(tab._next_button)
    layout.addWidget(tab._page_label, 1)
    return layout


def _build_review_controls(tab: SightingsTab) -> QHBoxLayout:
    """Crea el límite de revisión y los botones de revisar y auditar de `tab`."""
    tab._limit_spin = QSpinBox(tab)
    tab._limit_spin.setRange(MIN_REVIEW_LIMIT, MAX_REVIEW_LIMIT)
    tab._limit_spin.setValue(DEFAULT_REVIEW_LIMIT)
    tab._review_unverified_button = QPushButton("Revisar sin verificar", tab)
    tab._review_confirmed_button = QPushButton("Auditar confirmadas", tab)
    tab._review_unverified_button.clicked.connect(tab._on_review_unverified_clicked)
    tab._review_confirmed_button.clicked.connect(tab._on_review_confirmed_clicked)
    layout = QHBoxLayout()
    layout.addWidget(tab._limit_spin)
    layout.addWidget(tab._review_unverified_button)
    layout.addWidget(tab._review_confirmed_button)
    return layout


class SightingsTab(QWidget):
    """Pestaña para buscar avistamientos, ver su detalle y revisarlos."""

    # Asignados por `_build_pagination`/`_build_review_controls` (fuera de la clase, para no
    # superar el límite de líneas por clase de ARQUITECTURA §6).
    _prev_button: QPushButton
    _next_button: QPushButton
    _page_label: QLabel
    _limit_spin: QSpinBox
    _review_unverified_button: QPushButton
    _review_confirmed_button: QPushButton

    def __init__(self, session: GuiSession) -> None:
        """Construye la pestaña y ejecuta una búsqueda inicial sin filtros.

        Args:
            session: sesión de la GUI de la que se toman el navegador y los puertos.
        """
        super().__init__()
        self._session = session
        self._query = SightingQuery()
        self._page = 0
        self._build_ui()
        self.search()

    def current_query(self) -> SightingQuery:
        """Construye el filtro vigente, delegando en el widget de filtros.

        Raises:
            InvalidEntityError: si el rango de fechas está invertido.
        """
        return self._filters.current_query()

    def search(self) -> None:
        """Reconstruye el filtro y vuelve a la primera página de resultados."""
        try:
            query = self.current_query()
        except InvalidEntityError:
            QMessageBox.warning(self, DIALOG_TITLE, INVALID_RANGE_MESSAGE)
            return
        self._query = query
        self._page = 0
        self._load_page()

    def set_busy(self, busy: bool) -> None:
        """Deshabilita los botones de revisión mientras hay un procesamiento en curso."""
        self._review_unverified_button.setEnabled(not busy)
        self._review_confirmed_button.setEnabled(not busy)

    def review(self, status: ReviewStatus) -> None:
        """Revisa hasta el límite elegido de avistamientos en `status` y refresca la tabla."""
        limit = self._limit_spin.value()
        review_ui = QtReviewUI(self)
        try:
            summary = self._run_review(review_ui, limit, status)
        except (ReviewError, RepositoryError, CropStoreError, EncryptionError) as error:
            QMessageBox.warning(self, DIALOG_TITLE, str(error))
            return
        finally:
            review_ui.close()
        QMessageBox.information(self, DIALOG_TITLE, _summary_text(summary))
        self.search()

    def _run_review(self, review_ui: QtReviewUI, limit: int, status: ReviewStatus) -> ReviewSummary:
        """Ejecuta `ReviewSightings` con el diálogo Qt de revisión."""
        use_case = ReviewSightings(
            self._session.repository, self._session.crop_store, review_ui, self._session.clock
        )
        return use_case.execute(limit, status)

    def _load_page(self) -> None:
        """Consulta la página actual y actualiza la tabla, la etiqueta y el detalle."""
        offset = self._page * PAGE_SIZE
        try:
            total = self._session.browser.count_sightings(self._query)
            records = self._session.browser.search_sightings(self._query, PAGE_SIZE, offset)
        except RepositoryError as error:
            QMessageBox.warning(self, DIALOG_TITLE, str(error))
            return
        self._model.set_records(records)
        self._update_page_label(total)
        self._prev_button.setEnabled(self._page > 0)
        self._next_button.setEnabled((self._page + 1) * PAGE_SIZE < total)
        self._detail.clear()

    def _update_page_label(self, total: int) -> None:
        """Actualiza la etiqueta de paginación con el total de resultados."""
        if total == 0:
            self._page_label.setText(PAGE_LABEL_EMPTY)
            return
        total_pages = -(-total // PAGE_SIZE)
        self._page_label.setText(
            f"página {self._page + 1} de {total_pages} ({total} avistamientos)"
        )

    def _on_previous_clicked(self) -> None:
        """Retrocede una página si no es la primera."""
        if self._page > 0:
            self._page -= 1
            self._load_page()

    def _on_next_clicked(self) -> None:
        """Avanza a la siguiente página."""
        self._page += 1
        self._load_page()

    def _on_review_unverified_clicked(self) -> None:
        """Revisa los avistamientos sin verificar."""
        self.review(ReviewStatus.UNVERIFIED)

    def _on_review_confirmed_clicked(self) -> None:
        """Audita los avistamientos confirmados sin revisar."""
        self.review(ReviewStatus.CONFIRMED)

    def _on_row_selected(
        self,
        current: QModelIndex | QPersistentModelIndex,
        _previous: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Muestra el detalle y el recorte del avistamiento seleccionado."""
        self._detail.clear()
        if not current.isValid():
            return
        record = self._model.record_at(current.row())
        self._detail.show_record(record, self._session.crop_store)

    def _build_ui(self) -> None:
        """Crea y arma la pestaña componiendo los widgets de filtros, tabla y detalle."""
        self._filters = SightingsFilters(self)
        self._filters.search_requested.connect(self.search)
        self._model = SightingsTableModel(self)
        self._table = NoCopyTableView(self)
        self._table.setModel(self._model)
        selection_model = self._table.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_row_selected)
        self._detail = SightingsDetail(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._filters)
        layout.addWidget(self._table, 1)
        layout.addLayout(_build_pagination(self))
        layout.addWidget(self._detail)
        layout.addLayout(_build_review_controls(self))
