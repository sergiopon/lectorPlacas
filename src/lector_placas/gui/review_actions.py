"""Columna de acciones del panel de revisión (specs 048/053, ADR-015)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from lector_placas.gui.review_panel import ReviewPanel


def make_button(
    parent: QWidget, text: str, slot: Callable[[], None], role: str | None = None
) -> QPushButton:
    """Crea un botón conectado a `slot`, con el rol de estilo `role` si se indica."""
    button = QPushButton(text, parent)
    if role is not None:
        button.setProperty("role", role)
    button.clicked.connect(slot)
    return button


def make_actions(
    parent: QWidget, panel: ReviewPanel
) -> tuple[QWidget, tuple[QPushButton, ...], QLabel]:
    """Crea la columna de acciones de `panel` y su nota de espera."""
    specs = (
        ("✓ Es correcta   C", panel.confirm, "primary"),
        ("✎ Corregir   E", panel.start_edit, None),
        ("✗ No es una placa   R", panel.reject, None),
        ("◐ Placa borrosa   B", panel.mark_illegible, None),
        ("Saltar   S", panel.skip, "ghost"),
    )
    buttons = tuple(make_button(parent, text, slot, role) for text, slot, role in specs)
    note = QLabel("Espera a que termine el procesamiento para revisar.", parent)
    note.setProperty("role", "muted")
    note.setWordWrap(True)
    container, layout = make_column(parent)
    for button in buttons:
        layout.addWidget(button)
    layout.addWidget(note)
    return container, buttons, note


def make_column(parent: QWidget) -> tuple[QWidget, QVBoxLayout]:
    """Crea una columna vacía de widgets con márgenes nulos."""
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    return container, layout
