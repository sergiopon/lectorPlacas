"""Diálogos de las herramientas poco frecuentes: mantenimiento e historial (spec 049)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from lector_placas.domain.errors import RepositoryError
from lector_placas.gui.maintenance_tab import MaintenanceTab
from lector_placas.gui.runs_model import RunsTableModel
from lector_placas.gui.session import GuiSession
from lector_placas.gui.widgets import NoCopyTableView

TOOLS_TITLE: Final[str] = "Exportar, retención y métricas"
RUNS_TITLE: Final[str] = "Historial de videos"
RUNS_LIMIT: Final[int] = 200


class ToolsDialog(QDialog):
    """Diálogo modal con la pestaña de mantenimiento (spec 045)."""

    data_changed = Signal()

    def __init__(self, session: GuiSession, parent: QWidget | None) -> None:
        """Envuelve `MaintenanceTab` y un botón de cerrar."""
        super().__init__(parent)
        self.setWindowTitle(TOOLS_TITLE)
        self._maintenance = MaintenanceTab(session)
        self._maintenance.data_changed.connect(self.data_changed.emit)
        close = QPushButton("Cerrar", self)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self._maintenance, 1)
        layout.addWidget(close)

    def set_busy(self, busy: bool) -> None:
        """Reenvía el estado ocupado a la pestaña de mantenimiento."""
        self._maintenance.set_busy(busy)


class RunsDialog(QDialog):
    """Diálogo modal con las últimas corridas de procesamiento."""

    def __init__(self, session: GuiSession, parent: QWidget | None) -> None:
        """Muestra las últimas corridas o el error del repositorio."""
        super().__init__(parent)
        self.setWindowTitle(RUNS_TITLE)
        self._model = RunsTableModel(self)
        self._view = NoCopyTableView(self)
        self._view.setModel(self._model)
        self._message = QLabel(self)
        close = QPushButton("Cerrar", self)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._message)
        layout.addWidget(close)
        self._load(session)

    def _load(self, session: GuiSession) -> None:
        """Carga la tabla con las corridas recientes o muestra el error."""
        try:
            runs = session.browser.list_runs(RUNS_LIMIT, 0)
        except RepositoryError as error:
            self._message.setText(str(error))
            return
        self._model.set_runs(runs)
