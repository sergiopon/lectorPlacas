"""Ventana principal de la GUI con las tres pestañas que llenan las specs 043-045."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.gui.process_tab import ProcessTab
from lector_placas.gui.session import GuiSession
from lector_placas.gui.sightings_tab import SightingsTab

WINDOW_TITLE: Final[str] = "lectorPlacas"
TAB_TITLES: Final[tuple[str, str, str]] = ("Procesar", "Avistamientos", "Exportar y retención")
PLACEHOLDER_TEXT: Final[str] = "Disponible en una versión posterior"
CLOSE_BUSY_MESSAGE: Final[str] = "Hay un procesamiento en curso. ¿Cancelarlo y salir?"
WINDOW_WIDTH: Final[int] = 1200
WINDOW_HEIGHT: Final[int] = 800


class MainWindow(QMainWindow):
    """Ventana principal: pestañas vacías y barra de estado con el resultado de la purga."""

    busy_changed = Signal(bool)

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
        self._process_tab = ProcessTab(session)
        self._sightings_tab = SightingsTab(session)
        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._process_tab, TAB_TITLES[0])
        self._tabs.addTab(self._sightings_tab, TAB_TITLES[1])
        self._tabs.addTab(_placeholder_page(self._tabs), TAB_TITLES[2])
        self._process_tab.busy_changed.connect(self.set_busy)
        self.busy_changed.connect(self._sightings_tab.set_busy)
        self._process_tab.run_finished.connect(self._sightings_tab.search)
        self.setCentralWidget(self._tabs)
        self.statusBar().showMessage(
            f"Purga al abrir: recortes={purge.crops_deleted} "
            f"avistamientos={purge.sightings_deleted} corridas={purge.runs_deleted} "
            f"placas={purge.plates_deleted} exportaciones={purge.exports_deleted}"
        )

    def tabs(self) -> QTabWidget:
        """Devuelve el widget de pestañas para que las specs siguientes lo rellenen."""
        return self._tabs

    def set_busy(self, busy: bool) -> None:
        """Reenvía el estado ocupado de la pestaña de procesamiento.

        Las specs 044 y 045 se conectan a `busy_changed` para deshabilitar sus acciones
        de escritura mientras hay un procesamiento en curso.

        Args:
            busy: `True` si hay un procesamiento en curso.
        """
        self.busy_changed.emit(busy)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  (nombre impuesto por Qt)
        """Pregunta antes de cerrar si hay un procesamiento en curso y luego cierra la sesión.

        Args:
            event: evento de cierre de la ventana.
        """
        if not self._process_tab.is_busy():
            self._session.close()
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            WINDOW_TITLE,
            CLOSE_BUSY_MESSAGE,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.No:
            event.ignore()
            return
        self._process_tab.cancel()
        self._process_tab.wait_for_worker()
        self._session.close()
        event.accept()


def _placeholder_page(parent: QWidget) -> QWidget:
    """Crea una pestaña vacía con el aviso de que su contenido llega en otra versión."""
    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel(PLACEHOLDER_TEXT, page))
    return page
