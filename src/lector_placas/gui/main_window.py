"""Ventana principal de la GUI con las tres pestañas que llenan las specs 043-045."""

from __future__ import annotations

from typing import Final

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.gui.session import GuiSession

WINDOW_TITLE: Final[str] = "lectorPlacas"
TAB_TITLES: Final[tuple[str, str, str]] = ("Procesar", "Avistamientos", "Exportar y retención")
PLACEHOLDER_TEXT: Final[str] = "Disponible en una versión posterior"
WINDOW_WIDTH: Final[int] = 1200
WINDOW_HEIGHT: Final[int] = 800


class MainWindow(QMainWindow):
    """Ventana principal: pestañas vacías y barra de estado con el resultado de la purga."""

    def __init__(self, session: GuiSession, purge: PurgeResult) -> None:
        """Construye la ventana con sus pestañas y su barra de estado.

        Args:
            session: sesión abierta que se cierra al cerrar la ventana.
            purge: resultado de la purga por retención hecha al abrir la sesión.
        """
        super().__init__()
        self._session = session
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._tabs = QTabWidget(self)
        for title in TAB_TITLES:
            self._tabs.addTab(_placeholder_page(self._tabs), title)
        self.setCentralWidget(self._tabs)
        self.statusBar().showMessage(
            f"Purga al abrir: recortes={purge.crops_deleted} "
            f"avistamientos={purge.sightings_deleted} corridas={purge.runs_deleted} "
            f"placas={purge.plates_deleted} exportaciones={purge.exports_deleted}"
        )

    def tabs(self) -> QTabWidget:
        """Devuelve el widget de pestañas para que las specs siguientes lo rellenen."""
        return self._tabs

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  (nombre impuesto por Qt)
        """Cierra la sesión y acepta el evento de cierre.

        Args:
            event: evento de cierre de la ventana.
        """
        self._session.close()
        event.accept()


def _placeholder_page(parent: QWidget) -> QWidget:
    """Crea una pestaña vacía con el aviso de que su contenido llega en otra versión."""
    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel(PLACEHOLDER_TEXT, page))
    return page
