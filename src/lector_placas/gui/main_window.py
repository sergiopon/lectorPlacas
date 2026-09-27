"""Ventana principal: páginas Procesar y Lecturas, menú "Más" y cierre seguro (spec 049)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import SightingQuery
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.domain.entities import ReviewStatus
from lector_placas.domain.errors import RepositoryError
from lector_placas.gui.process_page import ProcessPage
from lector_placas.gui.readings_page import ReadingsPage
from lector_placas.gui.session import GuiSession
from lector_placas.gui.theme import BORDER, SURFACE
from lector_placas.gui.tools_dialogs import RUNS_TITLE, TOOLS_TITLE, RunsDialog, ToolsDialog

WINDOW_TITLE: Final[str] = "lectorPlacas"
PROCESS_PAGE: Final[str] = "procesar"
READINGS_PAGE: Final[str] = "lecturas"
PAGE_NAMES: Final[tuple[str, str]] = (PROCESS_PAGE, READINGS_PAGE)
NAV_LABELS: Final[tuple[str, str]] = ("Procesar", "Lecturas")
MORE_LABEL: Final[str] = "Más"
CLOSE_BUSY_MESSAGE: Final[str] = "Hay un procesamiento en curso. ¿Cancelarlo y salir?"
PURGE_MESSAGE: Final[str] = (
    "Al abrir se borraron {total} datos vencidos por la política de retención."
)
WINDOW_WIDTH: Final[int] = 1280
WINDOW_HEIGHT: Final[int] = 820


class MainWindow(QMainWindow):
    """Ventana con las páginas Procesar y Lecturas, menú "Más" y barra de estado."""

    busy_changed = Signal(bool)

    # Asignado por `_make_center` (clase ≤ 150 líneas, ARQUITECTURA §6).
    _more_button: QToolButton

    def __init__(self, session: GuiSession, purge: PurgeResult) -> None:
        """Construye la ventana, elige la página inicial y deja el menú "Más"."""
        super().__init__()
        self._session = session
        self._tools: ToolsDialog | None = None
        self._nav_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._process_page = ProcessPage(session)
        self._readings_page = ReadingsPage(session)
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._process_page)
        self._stack.addWidget(self._readings_page)
        self.setCentralWidget(_make_center(self))
        _connect(self)
        self._update_pending(self._readings_page.pending_count())
        self.show_page(self._initial_page())
        total = _purge_total(purge)
        if total:
            self.statusBar().showMessage(PURGE_MESSAGE.format(total=total))

    def show_page(self, name: str) -> None:
        """Muestra la página `name` (`"procesar"` o `"lecturas"`) y marca su botón."""
        self._stack.setCurrentIndex(PAGE_NAMES.index(name))
        for page_name, button in self._nav_buttons.items():
            button.setChecked(page_name == name)

    def current_page(self) -> str:
        """Devuelve el nombre de la página visible."""
        return PAGE_NAMES[self._stack.currentIndex()]

    def set_busy(self, busy: bool) -> None:
        """Reenvía el estado ocupado a la página de lecturas y a los diálogos abiertos."""
        self.busy_changed.emit(busy)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Pregunta antes de cerrar si hay un procesamiento en curso y cierra la sesión."""
        if not self._process_page.is_busy():
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
        self._process_page.cancel()
        self._process_page.wait_for_worker()
        self._session.close()
        event.accept()

    def _on_busy(self, busy: bool) -> None:
        """Actualiza el diálogo de herramientas abierto, si lo hay."""
        if self._tools is not None:
            self._tools.set_busy(busy)

    def _initial_page(self) -> str:
        """Devuelve `"lecturas"` si la base tiene avistamientos, o `"procesar"`."""
        try:
            total = self._session.browser.count_sightings(SightingQuery())
        except RepositoryError:
            return PROCESS_PAGE
        return READINGS_PAGE if total > 0 else PROCESS_PAGE

    def _update_pending(self, pending: int) -> None:
        """Actualiza el texto del botón "Lecturas" con el número de pendientes."""
        label = f"Lecturas ({pending} por revisar)" if pending > 0 else "Lecturas"
        self._nav_buttons[READINGS_PAGE].setText(label)

    def _open_review(self, run_id: object) -> None:
        """Abre "Lecturas" filtrada por la corrida cuyo botón se pulsó."""
        self._readings_page.show_run(_as_run_id(run_id), _pending_status(self._session, run_id))
        self.show_page(READINGS_PAGE)

    def _open_tools(self) -> None:
        """Abre el diálogo de exportar, retención y métricas como modal."""
        self._tools = ToolsDialog(self._session, self)
        self._tools.data_changed.connect(self._readings_page.reload)
        self._tools.set_busy(self._process_page.is_busy())
        try:
            self._tools.exec()
        finally:
            self._tools = None

    def _open_runs(self) -> None:
        """Abre el diálogo del historial de videos como modal."""
        RunsDialog(self._session, self).exec()


def _connect(window: MainWindow) -> None:
    """Conecta las señales de las páginas y del estado ocupado."""
    window._process_page.busy_changed.connect(window.set_busy)
    window._process_page.run_finished.connect(window._readings_page.reload)
    window._process_page.review_requested.connect(window._open_review)
    window._readings_page.pending_changed.connect(window._update_pending)
    window.busy_changed.connect(window._readings_page.set_busy)
    window.busy_changed.connect(window._on_busy)


def _make_nav(window: MainWindow, parent: QWidget) -> QHBoxLayout:
    """Crea los dos botones conmutables de navegación."""
    nav = QHBoxLayout()
    for name, label in zip(PAGE_NAMES, NAV_LABELS, strict=True):
        button = QPushButton(label, parent)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, page=name: window.show_page(page))
        window._nav_buttons[name] = button
        nav.addWidget(button)
    return nav


def _make_more_button(window: MainWindow, parent: QWidget) -> QToolButton:
    """Crea el botón "Más" con su menú de herramientas e historial."""
    button = QToolButton(parent)
    button.setText(MORE_LABEL)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(button)
    menu.addAction(f"{TOOLS_TITLE}…", window._open_tools)
    menu.addAction(f"{RUNS_TITLE}…", window._open_runs)
    button.setMenu(menu)
    return button


def _make_center(window: MainWindow) -> QWidget:
    """Crea el contenedor con la barra superior y la pila de páginas."""
    center = QWidget(window)
    bar = QWidget(center)
    bar.setObjectName("TopBar")
    bar.setStyleSheet(
        f"QWidget#TopBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}"
    )
    brand = QLabel(WINDOW_TITLE, bar)
    brand.setStyleSheet("font-weight: bold;")
    top = QHBoxLayout(bar)
    top.addWidget(brand)
    top.addStretch(1)
    top.addLayout(_make_nav(window, bar))
    top.addStretch(1)
    window._more_button = _make_more_button(window, bar)
    top.addWidget(window._more_button)
    layout = QVBoxLayout(center)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(bar)
    layout.addWidget(window._stack, 1)
    return center


def _purge_total(purge: PurgeResult) -> int:
    """Suma los conteos de lo borrado por la purga al abrir."""
    return (
        purge.crops_deleted
        + purge.sightings_deleted
        + purge.runs_deleted
        + purge.plates_deleted
        + purge.exports_deleted
        + purge.training_deleted
    )


def _as_run_id(value: object) -> int | None:
    """Convierte el `run_id` recibido por señal a `int | None`."""
    return value if isinstance(value, int) else None


def _pending_status(session: GuiSession, run_id: object) -> ReviewStatus | None:
    """Devuelve `UNVERIFIED` si la corrida tiene pendientes, o `None` si no."""
    if not isinstance(run_id, int):
        return None
    query = SightingQuery(status=ReviewStatus.UNVERIFIED, run_id=run_id)
    try:
        pending = session.browser.count_sightings(query)
    except RepositoryError:
        return None
    return ReviewStatus.UNVERIFIED if pending > 0 else None
