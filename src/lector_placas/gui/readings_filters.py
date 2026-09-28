"""Filtros de la página "Lecturas": estado, corrida y búsqueda por placa (spec 048)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from lector_placas.application.ports import RunRecord
from lector_placas.domain.entities import ReviewStatus
from lector_placas.gui.labels import profile_label

FILTER_ORDER: Final[tuple[ReviewStatus | None, ...]] = (
    ReviewStatus.UNVERIFIED,
    ReviewStatus.CONFIRMED,
    ReviewStatus.CORRECTED,
    ReviewStatus.REJECTED,
    ReviewStatus.ILLEGIBLE,
    None,
)
FILTER_LABELS: Final[Mapping[ReviewStatus | None, str]] = MappingProxyType(
    {
        ReviewStatus.UNVERIFIED: "Por revisar",
        ReviewStatus.CONFIRMED: "Confirmadas",
        ReviewStatus.CORRECTED: "Corregidas",
        ReviewStatus.REJECTED: "Descartadas",
        ReviewStatus.ILLEGIBLE: "Borrosas",
        None: "Todas",
    }
)
ALL_RUNS_LABEL: Final[str] = "Todos los videos"
SEARCH_PLACEHOLDER: Final[str] = "Buscar placa…"
DEBOUNCE_MS: Final[int] = 300
MAX_PLATE_CHARS: Final[int] = 10
PLATE_PATTERN: Final[str] = "^[A-Za-z0-9]{0,10}$"


class ReadingsFilters(QWidget):
    """Fila de filtros de la galería: estado, búsqueda por placa y corrida."""

    changed = Signal()

    _buttons: dict[ReviewStatus | None, QPushButton]
    _group: QButtonGroup
    _timer: QTimer
    _search: QLineEdit
    _runs: QComboBox

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea los filtros con "Por revisar" seleccionado y sin corrida ni búsqueda."""
        super().__init__(parent)
        self._buttons = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.changed.emit)
        _build_filters(self)

    def status(self) -> ReviewStatus | None:
        """Devuelve el estado elegido, o `None` para "Todas"."""
        for candidate in FILTER_ORDER:
            if self._buttons[candidate].isChecked():
                return candidate
        return None

    def set_status(self, status: ReviewStatus | None) -> None:
        """Marca el botón de `status` sin emitir `changed`."""
        for candidate, button in self._buttons.items():
            button.setChecked(candidate is status)

    def set_counts(self, counts: Mapping[ReviewStatus | None, int]) -> None:
        """Escribe en cada botón su nombre y su contador (0 si falta)."""
        for status in FILTER_ORDER:
            self._buttons[status].setText(f"{FILTER_LABELS[status]} ({counts.get(status, 0)})")

    def set_runs(self, runs: Sequence[RunRecord]) -> None:
        """Rellena el combo de videos conservando la corrida elegida si sigue en la lista."""
        previous = self.run_id()
        self._runs.blockSignals(True)
        self._runs.clear()
        self._runs.addItem(ALL_RUNS_LABEL, None)
        for run in runs:
            self._runs.addItem(_run_text(run), run.run_id)
        self._runs.blockSignals(False)
        self.set_run_id(previous)

    def run_id(self) -> int | None:
        """Devuelve la corrida elegida, o `None` para "Todos los videos"."""
        data = self._runs.currentData()
        return None if data is None else int(data)

    def set_run_id(self, run_id: int | None) -> None:
        """Marca la corrida `run_id` sin emitir `changed`; si no está, marca todas."""
        index = self._runs.findData(run_id) if run_id is not None else 0
        self._runs.blockSignals(True)
        self._runs.setCurrentIndex(max(index, 0))
        self._runs.blockSignals(False)

    def plate_prefix(self) -> str | None:
        """Devuelve el texto buscado en mayúsculas, o `None` si está vacío."""
        return self._search.text().upper() or None


def _build_filters(filters: ReadingsFilters) -> None:
    layout = QHBoxLayout(filters)
    for status in FILTER_ORDER:
        button = _make_filter_button(filters, status)
        filters._buttons[status] = button
        filters._group.addButton(button)
        layout.addWidget(button)
    filters._search = _make_search(filters)
    filters._runs = QComboBox(filters)
    filters._runs.addItem(ALL_RUNS_LABEL, None)
    filters._runs.currentIndexChanged.connect(lambda _index: filters.changed.emit())
    layout.addWidget(filters._search)
    layout.addWidget(filters._runs)
    filters.set_status(FILTER_ORDER[0])


def _make_filter_button(filters: ReadingsFilters, status: ReviewStatus | None) -> QPushButton:
    button = QPushButton(f"{FILTER_LABELS[status]} (0)", filters)
    button.setCheckable(True)
    button.clicked.connect(filters.changed.emit)
    return button


def _make_search(filters: ReadingsFilters) -> QLineEdit:
    search = QLineEdit(filters)
    search.setPlaceholderText(SEARCH_PLACEHOLDER)
    search.setMaxLength(MAX_PLATE_CHARS)
    search.setValidator(QRegularExpressionValidator(PLATE_PATTERN, filters))
    search.textChanged.connect(lambda _text: filters._timer.start())
    return search


def _run_text(run: RunRecord) -> str:
    started = run.started_at.astimezone().strftime("%d/%m %H:%M")
    return f"Video {run.run_id} · {started} · {profile_label(run.profile)}"
