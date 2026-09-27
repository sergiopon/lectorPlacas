"""Widgets reutilizables de la GUI (ADR-015)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QTableView, QWidget


class NoCopyTableView(QTableView):
    """Tabla de solo lectura sin menú contextual ni copiado al portapapeles (SEG-27)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea la tabla con selección de fila completa, sin edición ni menú contextual.

        Args:
            parent: widget padre, o `None`.
        """
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Descarta el atajo de copiar; el resto de teclas sigue a la implementación base.

        Args:
            event: evento de teclado.
        """
        if event.matches(QKeySequence.StandardKey.Copy):
            event.ignore()
            return
        super().keyPressEvent(event)
