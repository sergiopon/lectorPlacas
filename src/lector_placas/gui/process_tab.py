"""Pestaña "Procesar": elegir video y perfil, procesar en un hilo y listar las corridas."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ProgressUpdate
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError, RepositoryError
from lector_placas.gui.processing import ProcessingRequest, ProcessingWorker
from lector_placas.gui.runs_model import NOT_AVAILABLE, RUN_COLUMNS, RunsTableModel
from lector_placas.gui.session import GuiSession
from lector_placas.gui.widgets import NoCopyTableView

__all__ = ["RUN_COLUMNS", "ProcessTab", "RunsTableModel"]

RUNS_PAGE_SIZE: Final[int] = 50
STATUS_CANCELLING: Final[str] = "cancelando…"
STATUS_CANCELLED: Final[str] = "procesamiento cancelado"
DIALOG_TITLE: Final[str] = "lectorPlacas"
VIDEO_DIALOG_CAPTION: Final[str] = "Elegir video"

_Controls = tuple[
    QPushButton,
    QLabel,
    QComboBox,
    QPushButton,
    QPushButton,
    QProgressBar,
    QLabel,
    RunsTableModel,
    NoCopyTableView,
    QPushButton,
]


def _video_filter(extensions: Sequence[str]) -> str:
    """Construye el filtro `"Videos (*.mp4 *.mov …)"` a partir de las extensiones permitidas."""
    return "Videos (" + " ".join(f"*{extension}" for extension in extensions) + ")"


def _progress_text(update: ProgressUpdate) -> str:
    """Compone el texto de estado mientras avanza el procesamiento."""
    return (
        f"frames {update.frames_processed}/{update.frames_decoded} "
        f"· avistamientos {update.sightings_saved}"
    )


def _success_text(result: RunResult) -> str:
    """Compone el resumen final de una corrida exitosa."""
    stats = result.stats
    velocity = f"{stats.speed_factor:.2f}x" if stats.speed_factor is not None else NOT_AVAILABLE
    return (
        f"run_id={result.run_id} frames={stats.frames_processed}/{stats.frames_decoded} "
        f"confirmadas={stats.sightings_confirmed} sin_verificar={stats.sightings_unverified} "
        f"sin_lectura={stats.tracks_without_reading} velocidad={velocity}"
    )


def _make_controls(session: GuiSession, parent: QWidget) -> _Controls:
    """Crea los diez controles propios de la pestaña, en el orden que devuelve la tupla."""
    config = session.config
    profile_combo = QComboBox(parent)
    profile_combo.addItems(list(config.profiles))
    profile_combo.setCurrentText(config.profile(None)[0])
    cancel_button = QPushButton("Cancelar", parent)
    cancel_button.setEnabled(False)
    progress_bar = QProgressBar(parent)
    progress_bar.setRange(0, 0)
    model = RunsTableModel(parent)
    table_view = NoCopyTableView(parent)
    table_view.setModel(model)
    return (
        QPushButton("Elegir video…", parent),
        QLabel(parent),
        profile_combo,
        QPushButton("Procesar", parent),
        cancel_button,
        progress_bar,
        QLabel(parent),
        model,
        table_view,
        QPushButton("Actualizar", parent),
    )


def _wire_worker(tab: ProcessTab, worker: ProcessingWorker, thread: QThread) -> None:
    """Conecta las señales del worker a los slots de `tab`."""
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # `quit()` corre en el hilo del worker (conexión directa): si fuera encolada al hilo de
    # la GUI, `wait_for_worker()` (que bloquea con `thread.wait()`) nunca la procesaría.
    worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
    worker.progress.connect(tab._on_progress)
    worker.succeeded.connect(tab._on_succeeded)
    worker.cancelled.connect(tab._on_cancelled)
    worker.failed.connect(tab._on_failed)
    worker.finished.connect(tab._on_finished)


def _make_layout(controls: _Controls) -> QVBoxLayout:
    """Arma los layouts de la pestaña a partir de sus controles, en el mismo orden."""
    choose_button, file_label, profile_combo, process_button, cancel_button = controls[:5]
    progress_bar, status_label, _model, table_view, refresh_button = controls[5:]
    choose_row = QHBoxLayout()
    choose_row.addWidget(choose_button)
    choose_row.addWidget(file_label, 1)
    profile_row = QHBoxLayout()
    profile_row.addWidget(profile_combo)
    profile_row.addWidget(process_button)
    profile_row.addWidget(cancel_button)
    profile_row.addStretch(1)
    layout = QVBoxLayout()
    layout.addLayout(choose_row)
    layout.addLayout(profile_row)
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)
    layout.addWidget(table_view, 1)
    layout.addWidget(refresh_button)
    return layout


class ProcessTab(QWidget):
    """Pestaña para elegir video y perfil, procesar en un hilo y ver las corridas."""

    busy_changed = Signal(bool)
    run_finished = Signal()

    def __init__(self, session: GuiSession) -> None:
        """Construye la pestaña con sus controles y la tabla de corridas.

        Args:
            session: sesión de la GUI de la que se toman config, claves y navegador.
        """
        super().__init__()
        self._session = session
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._video: Path | None = None
        self._busy = False
        self._build_ui()
        self.refresh_runs()

    def is_busy(self) -> bool:
        """Indica si hay un procesamiento en curso."""
        return self._busy

    def start(self, video: Path, profile_name: str) -> None:
        """Arranca el procesamiento de `video` con `profile_name` en un `QThread`.

        Si ya hay un procesamiento en curso no hace nada.

        Args:
            video: ruta ya validada del video a procesar.
            profile_name: nombre del perfil de escenario a usar.
        """
        if self.is_busy():
            return
        thread = QThread(self)
        worker = ProcessingWorker(
            self._session.config, self._session.keys, ProcessingRequest(video, profile_name)
        )
        _wire_worker(self, worker, thread)
        self._thread = thread
        self._worker = worker
        thread.start()
        self._set_busy(True)

    def cancel(self) -> None:
        """Pide cancelar el procesamiento en curso y deshabilita el botón "Cancelar"."""
        if self._worker is not None:
            self._worker.request_cancel()
        self._cancel_button.setEnabled(False)
        self._status_label.setText(STATUS_CANCELLING)

    def wait_for_worker(self) -> None:
        """Bloquea hasta que el hilo de procesamiento termine, si hay uno."""
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.wait()

    def refresh_runs(self) -> None:
        """Recarga la tabla de corridas desde el navegador de la sesión."""
        try:
            runs = self._session.browser.list_runs(RUNS_PAGE_SIZE, 0)
        except RepositoryError as error:
            self._status_label.setText(str(error))
            return
        self._model.set_runs(runs)

    def _build_ui(self) -> None:
        """Crea los controles, arma el layout y conecta las señales de la pestaña."""
        controls = _make_controls(self._session, self)
        (
            self._choose_button,
            self._file_label,
            self._profile_combo,
            self._process_button,
            self._cancel_button,
            self._progress_bar,
            self._status_label,
            self._model,
            self._table_view,
            self._refresh_button,
        ) = controls
        self.setLayout(_make_layout(controls))
        self._choose_button.clicked.connect(self._on_choose_clicked)
        self._process_button.clicked.connect(self._on_process_clicked)
        self._cancel_button.clicked.connect(self.cancel)
        self._refresh_button.clicked.connect(self.refresh_runs)

    def _on_choose_clicked(self) -> None:
        """Abre el diálogo de archivo y muestra el nombre del video elegido."""
        config = self._session.config
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            VIDEO_DIALOG_CAPTION,
            str(config.under_root(config.input.allowed_dirs[0])),
            _video_filter(config.input.allowed_extensions),
        )
        if not filename:
            return
        self._video = Path(filename)
        self._file_label.setText(self._video.name)

    def _on_process_clicked(self) -> None:
        """Valida el video elegido y, si es válido, arranca el procesamiento."""
        if self._video is None:
            return
        try:
            video = composition.validated_video(self._session.config, self._video)
        except LectorPlacasError as error:
            QMessageBox.warning(self, DIALOG_TITLE, str(error))
            return
        self.start(video, self._profile_combo.currentText())

    def _set_busy(self, busy: bool) -> None:
        """Actualiza el estado ocupado y habilita o deshabilita los controles."""
        self._busy = busy
        self._choose_button.setEnabled(not busy)
        self._profile_combo.setEnabled(not busy)
        self._process_button.setEnabled(not busy)
        self._cancel_button.setEnabled(busy)
        self.busy_changed.emit(busy)

    def _on_progress(self, update: ProgressUpdate) -> None:
        """Actualiza la barra y la etiqueta de estado con el avance recibido."""
        fraction = update.fraction
        if fraction is None:
            self._progress_bar.setRange(0, 0)
        else:
            self._progress_bar.setRange(0, 1000)
            self._progress_bar.setValue(round(fraction * 1000))
        self._status_label.setText(_progress_text(update))

    def _on_succeeded(self, result: RunResult) -> None:
        """Muestra el resumen final de la corrida exitosa."""
        self._status_label.setText(_success_text(result))

    def _on_cancelled(self) -> None:
        """Muestra el aviso de procesamiento cancelado."""
        self._status_label.setText(STATUS_CANCELLED)

    def _on_failed(self, message: str) -> None:
        """Muestra el error del procesamiento en un diálogo de aviso."""
        QMessageBox.warning(self, DIALOG_TITLE, message)

    def _on_finished(self) -> None:
        """Restablece los controles, refresca las corridas y avisa del fin del hilo."""
        self._set_busy(False)
        self.refresh_runs()
        self.run_finished.emit()
