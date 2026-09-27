"""Vistas del flujo de procesar un video: inicio, en curso y resumen (spec 049, ADR-015)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ProgressUpdate
from lector_placas.application.process_video import RunResult
from lector_placas.domain.entities import SightingRecord
from lector_placas.gui.card_grid import CardGrid
from lector_placas.gui.labels import PROFILE_LABELS, profile_label, short_time
from lector_placas.gui.theme import BORDER, SURFACE
from lector_placas.infrastructure.config import AppConfig

MIN_FRACTION: Final[float] = 0.02
FOUND: Final[str] = "placas encontradas"

Crops = Mapping[int, QPixmap | None]


def eta_text(elapsed_s: float, fraction: float | None) -> str | None:
    """Estima el tiempo restante como `"quedan ~m:ss"`, o `None` si no se puede."""
    if fraction is None or fraction < MIN_FRACTION:
        return None
    return f"quedan ~{short_time(round(elapsed_s * (1 - fraction) / fraction * 1000))}"


def _label(text: str, role: str, parent: QWidget) -> QLabel:
    """Crea una etiqueta con el rol de estilo indicado."""
    label = QLabel(text, parent)
    label.setProperty("role", role)
    return label


def _button(text: str, role: str, parent: QWidget, slot: Callable[[], None]) -> QPushButton:
    """Crea un botón con su rol de estilo y conectado a `slot`."""
    button = QPushButton(text, parent)
    button.setProperty("role", role)
    button.clicked.connect(slot)
    return button


def _row(*widgets: QWidget) -> QHBoxLayout:
    """Crea una fila horizontal con los widgets indicados y un hueco al final."""
    row = QHBoxLayout()
    for widget in widgets:
        row.addWidget(widget)
    row.addStretch(1)
    return row


def _dropped_video(mime: QMimeData, extensions: Sequence[str]) -> Path | None:
    """Ruta soltada si es un único archivo local con extensión permitida; si no, `None`."""
    urls = mime.urls() if mime.hasUrls() else []
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return path if path.suffix.lower() in extensions else None


class IdleView(QWidget):
    """Vista de inicio: elegir o arrastrar el video y el tipo de escena."""

    video_chosen = Signal(object)
    start_requested = Signal()
    change_requested = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """Crea la tarjeta de inicio con el video y los perfiles por elegir."""
        super().__init__(parent)
        self._config = config
        self._video: Path | None = None
        self._radios: dict[str, QRadioButton] = {}
        self._details: QWidget
        self._name_label: QLabel
        self._error_label: QLabel
        self.setAcceptDrops(True)
        _build_idle(self)

    def select_video(self, path: Path | None) -> None:
        """Muestra el video elegido, o vuelve al inicio si `path` es `None`."""
        self._video = path
        self._error_label.setVisible(False)
        self._details.setVisible(path is not None)
        if path is not None:
            self._name_label.setText(path.name)

    def show_error(self, message: str) -> None:
        """Muestra `message` en rojo debajo del botón, sin abrir ningún diálogo."""
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def selected_profile(self) -> str:
        """Devuelve la clave del perfil marcado, o el de por defecto si no hay ninguno."""
        marked = [name for name, radio in self._radios.items() if radio.isChecked()]
        return marked[0] if marked else self._config.profile(None)[0]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (nombre de Qt)
        """Acepta el arrastre solo si trae un único archivo local permitido."""
        if _dropped_video(event.mimeData(), self._config.input.allowed_extensions) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Pasa el video soltado a quien valida la ruta."""
        path = _dropped_video(event.mimeData(), self._config.input.allowed_extensions)
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.video_chosen.emit(path)

    def _on_choose_clicked(self) -> None:
        """Abre el diálogo de archivo y pasa la ruta elegida a quien la valida."""
        config = self._config
        allowed = config.input.allowed_extensions
        start = config.under_root(config.input.allowed_dirs[0])
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            "Elegir video",
            str(start),
            "Videos (" + " ".join(f"*{extension}" for extension in allowed) + ")",
        )
        if filename:
            self.video_chosen.emit(Path(filename))


def _build_idle(view: IdleView) -> None:
    """Arma la tarjeta centrada de la vista de inicio."""
    title = _label("Procesar un video", "title", view)
    hint = _label("Arrastra un video aquí o elígelo desde tu equipo.", "muted", view)
    choose = _button("Elegir video…", "primary", view, view._on_choose_clicked)
    view._error_label = QLabel(view)
    view._error_label.setStyleSheet("color: #991B1B;")
    view._details = QWidget(view)
    _build_profiles(view)
    card = QFrame(view)
    card.setObjectName("ProcessCard")
    style = f"QFrame#ProcessCard {{ background: {SURFACE}; border: 1px solid {BORDER};"
    card.setStyleSheet(f"{style} border-radius: 10px; }}")
    card.setMaximumWidth(560)
    layout = QVBoxLayout(card)
    for widget in (title, hint, choose, view._error_label, view._details):
        layout.addWidget(widget)
    outer = QVBoxLayout(view)
    outer.addStretch(1)
    outer.addWidget(card, 3, Qt.AlignmentFlag.AlignHCenter)
    outer.addStretch(1)
    view.select_video(None)


def _build_profiles(view: IdleView) -> None:
    """Crea el nombre del video, la pregunta de escena, los radios y los botones."""
    view._name_label = _label("", "title", view._details)
    layout = QVBoxLayout(view._details)
    layout.addWidget(view._name_label)
    layout.addWidget(QLabel("¿Dónde se grabó?", view._details))
    default = view._config.profile(None)[0]
    for name in view._config.profiles:
        radio = QRadioButton(profile_label(name), view._details)
        radio.setChecked(name == default)
        view._radios[name] = radio
        layout.addWidget(radio)
        if name in PROFILE_LABELS:
            description = _label(PROFILE_LABELS[name][1], "muted", view._details)
            layout.addWidget(description)
    start_button = _button("Empezar", "primary", view._details, view.start_requested.emit)
    change_button = _button("Cambiar video", "ghost", view._details, view.change_requested.emit)
    layout.addLayout(_row(start_button, change_button))


class RunningView(QWidget):
    """Vista en curso: progreso, cancelación y galería de placas en vivo."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea la vista con su barra, su contador, su botón y su galería."""
        super().__init__(parent)
        self._title = _label("", "title", self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)
        self._count = _label("", "muted", self)
        self._cancel_button = _button("Cancelar", "ghost", self, self.cancel_requested.emit)
        self._grid = CardGrid(self)
        self._grid.set_empty_message(
            "Buscando placas…", "Las placas aparecerán aquí a medida que se encuentren."
        )
        layout = QVBoxLayout(self)
        for widget in (self._title, self._bar, self._count, self._cancel_button):
            layout.addWidget(widget)
        layout.addWidget(self._grid, 1)

    def start(self, video_name: str) -> None:
        """Prepara la vista para una corrida nueva."""
        self._title.setText(f"Procesando {video_name}")
        self._bar.setRange(0, 0)
        self._count.setText(f"0 {FOUND}")
        self._cancel_button.setText("Cancelar")
        self._cancel_button.setEnabled(True)
        self._grid.set_records([], {})

    def set_progress(self, update: ProgressUpdate, elapsed_s: float) -> None:
        """Actualiza barra, contador y ETA con el avance recibido."""
        fraction = update.fraction
        if fraction is None:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 1000)
            self._bar.setValue(round(fraction * 1000))
        text = f"{update.sightings_saved} {FOUND}"
        eta = eta_text(elapsed_s, fraction)
        self._count.setText(text if eta is None else f"{text} · {eta}")

    def set_cancelling(self) -> None:
        """Deshabilita el botón de cancelar y lo deja en "Cancelando…"."""
        self._cancel_button.setEnabled(False)
        self._cancel_button.setText("Cancelando…")

    def set_records(self, records: Sequence[SightingRecord], crops: Crops) -> None:
        """Reemplaza las tarjetas de la galería en vivo."""
        self._grid.set_records(records, crops)


class DoneView(QWidget):
    """Vista de resumen: resultado de la corrida y siguientes pasos."""

    review_requested = Signal()
    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea la vista con su título, su resumen, sus botones y su galería."""
        super().__init__(parent)
        self._title = _label("", "title", self)
        self._summary = _label("", "muted", self)
        self._review_button = _button("Ver lecturas", "primary", self, self.review_requested.emit)
        self._restart_button = _button(
            "Procesar otro video", "ghost", self, self.restart_requested.emit
        )
        self._grid = CardGrid(self)
        self._grid.set_empty_message(
            "Sin placas guardadas", "Esta corrida no dejó placas que mostrar."
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._summary)
        layout.addLayout(_row(self._review_button, self._restart_button))
        layout.addWidget(self._grid, 1)

    def show_success(self, result: RunResult) -> None:
        """Muestra el resumen de una corrida exitosa con su botón de revisión."""
        stats = result.stats
        pending = stats.sightings_unverified
        self._title.setText(f"Listo: {stats.sightings_confirmed + pending} {FOUND}")
        self._summary.setText(
            f"{stats.sightings_confirmed} confirmadas automáticamente · {pending} por revisar ·"
            f" {stats.tracks_without_reading} vehículos sin placa legible"
        )
        label = f"Revisar {pending} placas pendientes" if pending > 0 else "Ver lecturas"
        self._review_button.setText(label)

    def show_cancelled(self) -> None:
        """Muestra el resumen de una corrida cancelada."""
        self._title.setText("Procesamiento cancelado")
        self._summary.setText("Las placas encontradas hasta ahora se guardaron.")
        self._review_button.setText("Ver lecturas")

    def set_records(self, records: Sequence[SightingRecord], crops: Crops) -> None:
        """Reemplaza las tarjetas de la galería de la corrida terminada."""
        self._grid.set_records(records, crops)
