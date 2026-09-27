"""Cuadrícula de tarjetas con selección y navegación por teclado (spec 047, ADR-015)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lector_placas.domain.entities import SightingRecord
from lector_placas.gui.plate_card import CARD_WIDTH, PlateCard

GRID_SPACING: Final[int] = 12
EMPTY_TITLE: Final[str] = "Nada por aquí"
EMPTY_HINT: Final[str] = ""

_ARROW_KEYS: Final[frozenset[int]] = frozenset(
    {
        int(Qt.Key.Key_Left),
        int(Qt.Key.Key_Right),
        int(Qt.Key.Key_Up),
        int(Qt.Key.Key_Down),
    }
)


def columns_for_width(width: int) -> int:
    """Calcula cuántas tarjetas caben a lo ancho.

    Args:
        width: ancho disponible, en píxeles.

    Returns:
        El número de columnas, nunca menor que 1.
    """
    return max(1, (width + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING))


class EmptyState(QWidget):
    """Aviso centrado que se muestra cuando la cuadrícula no tiene tarjetas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea el aviso con el mensaje por defecto."""
        super().__init__(parent)
        self._title_label = QLabel(EMPTY_TITLE, self)
        self._title_label.setProperty("role", "title")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label = QLabel(EMPTY_HINT, self)
        self._hint_label.setProperty("role", "muted")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self._title_label)
        layout.addWidget(self._hint_label)
        layout.addStretch(1)

    def set_message(self, title: str, hint: str) -> None:
        """Cambia el título y la pista del aviso.

        Args:
            title: título en una línea.
            hint: pista breve, con ajuste de línea.
        """
        self._title_label.setText(title)
        self._hint_label.setText(hint)


def _build_body(owner: QWidget) -> tuple[EmptyState, QWidget, QGridLayout, QStackedWidget]:
    """Crea el aviso, el contenedor de la cuadrícula y la pila que alterna entre ambos."""
    empty = EmptyState(owner)
    container = QWidget(owner)
    layout = QGridLayout(container)
    layout.setSpacing(GRID_SPACING)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    stack = QStackedWidget(owner)
    stack.addWidget(empty)
    stack.addWidget(container)
    return empty, container, layout, stack


class CardGrid(QScrollArea):
    """Cuadrícula desplazable de tarjetas de placa, con una tarjeta seleccionada."""

    selection_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea la cuadrícula vacía, con su aviso de vacío."""
        super().__init__(parent)
        self._cards: dict[int, PlateCard] = {}
        self._selected: int | None = None
        self._columns = 1
        self._empty, self._container, self._grid, self._stack = _build_body(self)
        self.setWidget(self._stack)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_empty_state()

    def set_records(
        self, records: Sequence[SightingRecord], crops: Mapping[int, QPixmap | None]
    ) -> None:
        """Reemplaza las tarjetas por las de `records` y conserva la selección si sigue."""
        previous = self._selected
        self._clear_cards()
        self._add_cards(records, crops)
        if previous is not None and previous in self._cards:
            self._apply_selection(previous, emit=False)
        self._relayout()
        self._update_empty_state()

    def append_records(
        self, records: Sequence[SightingRecord], crops: Mapping[int, QPixmap | None]
    ) -> None:
        """Añade al final las tarjetas de `records`, sin tocar las existentes."""
        self._add_cards(records, crops)
        self._relayout()
        self._update_empty_state()

    def update_record(self, record: SightingRecord) -> None:
        """Actualiza la tarjeta de `record` si existe; si no, no hace nada."""
        card = self._cards.get(record.sighting_id)
        if card is not None:
            card.update_record(record)

    def remove(self, sighting_id: int) -> None:
        """Quita la tarjeta de `sighting_id` y recoloca el resto; si no existe, no hace nada."""
        card = self._cards.pop(sighting_id, None)
        if card is None:
            return
        self._grid.removeWidget(card)
        card.setParent(None)
        card.deleteLater()
        if self._selected == sighting_id:
            self._selected = None
        self._relayout()
        self._update_empty_state()

    def ids(self) -> list[int]:
        """Devuelve los identificadores en el orden visible."""
        return list(self._cards)

    def select(self, sighting_id: int | None) -> None:
        """Selecciona la tarjeta indicada y emite si la selección cambió."""
        if sighting_id is None or sighting_id not in self._cards:
            self._apply_selection(None)
            return
        self._apply_selection(sighting_id)

    def selected_id(self) -> int | None:
        """Devuelve el identificador de la tarjeta seleccionada, o `None`."""
        return self._selected

    def next_id(self, sighting_id: int) -> int | None:
        """Devuelve el id siguiente, el anterior si era el último, o `None`."""
        order = list(self._cards)
        if sighting_id not in self._cards or len(order) == 1:
            return None
        index = order.index(sighting_id)
        return order[index - 1] if index == len(order) - 1 else order[index + 1]

    def set_empty_message(self, title: str, hint: str) -> None:
        """Cambia el mensaje que se muestra cuando no hay tarjetas."""
        self._empty.set_message(title, hint)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Recoloca las tarjetas si al cambiar el ancho cambia el número de columnas."""
        super().resizeEvent(event)
        if columns_for_width(self.viewport().width()) != self._columns:
            self._relayout()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Mueve la selección con las flechas; el resto de teclas sigue a la base."""
        if event.key() in _ARROW_KEYS:
            _move_selection(self, event.key())
            return
        super().keyPressEvent(event)

    def _apply_selection(self, sighting_id: int | None, *, emit: bool = True) -> None:
        changed = self._selected != sighting_id
        previous = self._cards.get(self._selected) if self._selected is not None else None
        card = self._cards.get(sighting_id) if sighting_id is not None else None
        if changed:
            self._selected = sighting_id
            if previous is not None:
                previous.set_selected(False)
            if card is not None:
                card.set_selected(True)
        if card is not None:
            self.ensureWidgetVisible(card)
        if changed and emit and sighting_id is not None:
            self.selection_changed.emit(sighting_id)

    def _add_cards(
        self, records: Sequence[SightingRecord], crops: Mapping[int, QPixmap | None]
    ) -> None:
        for record in records:
            card = PlateCard(record, crops.get(record.sighting_id), self._container)
            card.clicked.connect(self.select)
            self._cards[record.sighting_id] = card

    def _clear_cards(self) -> None:
        for card in self._cards.values():
            self._grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._selected = None

    def _relayout(self) -> None:
        self._columns = columns_for_width(self.viewport().width())
        for position, card in enumerate(self._cards.values()):
            self._grid.addWidget(card, position // self._columns, position % self._columns)

    def _update_empty_state(self) -> None:
        self._stack.setCurrentWidget(self._container if self._cards else self._empty)


def _move_selection(grid: CardGrid, key: int) -> None:
    """Mueve la selección de `grid` a la tarjeta vecina según la flecha pulsada."""
    order = list(grid._cards)
    if not order:
        return
    if grid._selected is None:
        grid.select(order[0])
        return
    index = order.index(grid._selected)
    if key == Qt.Key.Key_Right:
        target = min(index + 1, len(order) - 1)
    elif key == Qt.Key.Key_Left:
        target = max(index - 1, 0)
    elif key == Qt.Key.Key_Down:
        target = min(index + grid._columns, len(order) - 1)
    else:
        target = max(index - grid._columns, 0)
    grid.select(order[target])
