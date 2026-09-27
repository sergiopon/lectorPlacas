"""Widget de filtros de la pestaña "Avistamientos": construye la `SightingQuery` vigente."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import ReviewStatus
from lector_placas.gui.labels import STATUS_LABELS

STATUS_ALL_LABEL: Final[str] = "Todos"
MAX_RUN_ID: Final[int] = 2_147_483_647
PLATE_FILTER_PATTERN: Final[str] = "^[A-Za-z0-9]{0,10}$"
MAX_PLATE_CHARS: Final[int] = 10


class SightingsFilters(QWidget):
    """Filtros de la búsqueda de avistamientos: estado, placa, corrida y rango de fechas."""

    search_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea los controles de filtro, todos con sus valores por defecto.

        Args:
            parent: widget padre, o `None`.
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        for widget in self._create_widgets():
            layout.addWidget(widget)

    def current_query(self) -> SightingQuery:
        """Construye el filtro vigente a partir de los controles.

        Raises:
            InvalidEntityError: si el rango de fechas está invertido.
        """
        created_from = self._from_datetime() if self._from_check.isChecked() else None
        created_to = self._to_datetime() if self._to_check.isChecked() else None
        return SightingQuery(
            self._selected_status(),
            self._plate_edit.text().upper() or None,
            self._run_spin.value() or None,
            created_from,
            created_to,
        )

    def reset(self) -> None:
        """Restablece todos los filtros a sus valores por defecto."""
        self._status_combo.setCurrentIndex(0)
        self._plate_edit.clear()
        self._run_spin.setValue(0)
        self._from_check.setChecked(False)
        self._to_check.setChecked(False)

    def _selected_status(self) -> ReviewStatus | None:
        """Estado elegido en el combo, o `None` para "Todos"."""
        index = self._status_combo.currentIndex()
        if index == 0:
            return None
        return tuple(ReviewStatus)[index - 1]

    def _from_datetime(self) -> datetime:
        """Medianoche local del día elegido como inicio del rango."""
        date = self._from_date.date()
        return datetime(date.year(), date.month(), date.day()).astimezone()

    def _to_datetime(self) -> datetime:
        """Medianoche local del día siguiente al elegido como fin del rango."""
        date = self._to_date.date().addDays(1)
        return datetime(date.year(), date.month(), date.day()).astimezone()

    def _create_widgets(self) -> tuple[QWidget, ...]:
        """Crea todos los widgets de filtro y devuelve el orden en que se muestran."""
        self._create_status_combo()
        self._create_plate_edit()
        self._create_run_spin()
        self._create_date_filters()
        self._create_filter_buttons()
        return (
            self._status_combo,
            self._plate_edit,
            self._run_spin,
            self._from_check,
            self._from_date,
            self._to_check,
            self._to_date,
            self._search_button,
            self._clear_button,
        )

    def _create_status_combo(self) -> None:
        """Crea el combo de estado con "Todos" y los cuatro estados de revisión."""
        self._status_combo = QComboBox(self)
        self._status_combo.addItem(STATUS_ALL_LABEL)
        for status in ReviewStatus:
            self._status_combo.addItem(STATUS_LABELS[status])

    def _create_plate_edit(self) -> None:
        """Crea el campo de placa, validado y en mayúsculas."""
        self._plate_edit = QLineEdit(self)
        self._plate_edit.setMaxLength(MAX_PLATE_CHARS)
        self._plate_edit.setValidator(QRegularExpressionValidator(PLATE_FILTER_PATTERN, self))

    def _create_run_spin(self) -> None:
        """Crea el selector de corrida; `0` significa "todas"."""
        self._run_spin = QSpinBox(self)
        self._run_spin.setRange(0, MAX_RUN_ID)
        self._run_spin.setSpecialValueText("todas")

    def _create_date_filters(self) -> None:
        """Crea las casillas y selectores de fecha "desde" y "hasta", desactivados."""
        self._from_check = QCheckBox("Desde", self)
        self._from_date = QDateEdit(self)
        self._from_date.setCalendarPopup(True)
        self._from_date.setEnabled(False)
        self._to_check = QCheckBox("Hasta", self)
        self._to_date = QDateEdit(self)
        self._to_date.setCalendarPopup(True)
        self._to_date.setEnabled(False)
        self._from_check.toggled.connect(self._from_date.setEnabled)
        self._to_check.toggled.connect(self._to_date.setEnabled)

    def _create_filter_buttons(self) -> None:
        """Crea los botones "Buscar" y "Limpiar"."""
        self._search_button = QPushButton("Buscar", self)
        self._clear_button = QPushButton("Limpiar", self)
        self._search_button.clicked.connect(self.search_requested.emit)
        self._clear_button.clicked.connect(self._on_clear_clicked)

    def _on_clear_clicked(self) -> None:
        """Restablece los filtros y pide una nueva búsqueda."""
        self.reset()
        self.search_requested.emit()
