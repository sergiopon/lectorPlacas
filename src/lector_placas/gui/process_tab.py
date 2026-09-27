"""Pestaña "Procesar": elegir video y perfil, procesar en un hilo y listar las corridas."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ProgressUpdate, RunRecord, RunStatus
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError, RepositoryError
from lector_placas.gui.processing import ProcessingRequest, ProcessingWorker
from lector_placas.gui.session import GuiSession

RUNS_PAGE_SIZE: Final[int] = 50
RUN_COLUMNS: Final[tuple[str, ...]] = (
    "Corrida",
    "Inicio",
    "Perfil",
    "Estado",
    "Duración",
    "Confirmadas",
    "Sin verificar",
    "Sin lectura",
    "Velocidad",
)
STATUS_CANCELLING: Final[str] = "cancelando…"
STATUS_CANCELLED: Final[str] = "procesamiento cancelado"
NOT_AVAILABLE: Final[str] = "n/d"
DIALOG_TITLE: Final[str] = "lectorPlacas"
VIDEO_DIALOG_CAPTION: Final[str] = "Elegir video"

_STATUS_TEXT: Final[dict[RunStatus, str]] = {
    RunStatus.COMPLETED: "completada",
    RunStatus.FAILED: "fallida",
    RunStatus.RUNNING: "en curso",
}


def _format_duration(duration_ms: int | None) -> str:
    """Formatea una duración de video en `mm:ss` o `n/d` si se desconoce."""
    if duration_ms is None:
        return NOT_AVAILABLE
    minutes, seconds = divmod(duration_ms // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_count(value: int | None) -> str:
    """Formatea un conteo entero o `n/d` si se desconoce."""
    return NOT_AVAILABLE if value is None else str(value)


def _format_velocity(duration_ms: int | None, processing_ms: int | None) -> str:
    """Formatea la velocidad de procesamiento como `d.dd x` o `n/d` si falta algún dato."""
    if duration_ms is None or processing_ms is None or processing_ms == 0:
        return NOT_AVAILABLE
    return f"{duration_ms / processing_ms:.2f}x"


def _video_filter(extensions: Sequence[str]) -> str:
    """Construye el filtro `"Videos (*.mp4 *.mov …)"` a partir de las extensiones permitidas."""
    return "Videos (" + " ".join(f"*{extension}" for extension in extensions) + ")"


class RunsTableModel(QAbstractTableModel):
    """Modelo de tabla de solo lectura con una fila por `RunRecord`."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Crea un modelo vacío.

        Args:
            parent: objeto padre del modelo.
        """
        super().__init__(parent)
        self._runs: tuple[RunRecord, ...] = ()

    def set_runs(self, runs: Sequence[RunRecord]) -> None:
        """Reemplaza las corridas mostradas por `runs`."""
        self.beginResetModel()
        self._runs = tuple(runs)
        self.endResetModel()

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de filas (una por corrida)."""
        return len(self._runs)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de columnas, fijo e igual a `RUN_COLUMNS`."""
        return len(RUN_COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Texto de la celda `index` para el rol de visualización."""
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        return self._cell_text(self._runs[index.row()], index.column())

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Título de la columna `section` en orientación horizontal."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return RUN_COLUMNS[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Solo lectura: las celdas se pueden seleccionar pero no editar."""
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _cell_text(self, run: RunRecord, column: int) -> str:
        """Devuelve el texto de la celda de `run` en la columna `column`."""
        values = (
            str(run.run_id),
            run.started_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            run.profile,
            _STATUS_TEXT[run.status],
            _format_duration(run.duration_ms),
            _format_count(run.sightings_confirmed),
            _format_count(run.sightings_unverified),
            _format_count(run.tracks_without_reading),
            _format_velocity(run.duration_ms, run.processing_ms),
        )
        return values[column]


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
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # Conexión directa: `quit()` es seguro entre hilos y debe ejecutarse en el hilo del
        # worker al final de `run()`. Si fuera encolada al hilo de la GUI, `wait_for_worker()`
        # (que bloquea con `thread.wait()`) nunca llegaría a procesarla y se colgaría.
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_succeeded)
        worker.cancelled.connect(self._on_cancelled)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        self._thread = thread
        self._worker = worker
        thread.start()
        self._set_busy(True)

    def cancel(self) -> None:
        """Pide cancelar el procesamiento en curso y deshabilita el botón "Cancelar"."""
        worker = self._worker
        if worker is not None:
            worker.request_cancel()
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
        """Crea y conecta los controles de la pestaña."""
        self._create_controls()
        layout = self._create_layout()
        self.setLayout(layout)
        self._connect_signals()

    def _create_controls(self) -> None:
        """Crea todos los controles de la pestaña."""
        config = self._session.config
        self._choose_button = QPushButton("Elegir video…", self)
        self._file_label = QLabel(self)
        self._profile_combo = QComboBox(self)
        self._profile_combo.addItems(list(config.profiles))
        self._profile_combo.setCurrentText(config.profile(None)[0])
        self._process_button = QPushButton("Procesar", self)
        self._cancel_button = QPushButton("Cancelar", self)
        self._cancel_button.setEnabled(False)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 0)
        self._status_label = QLabel(self)
        self._model = RunsTableModel(self)
        self._table_view = QTableView(self)
        self._table_view.setModel(self._model)
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._refresh_button = QPushButton("Actualizar", self)

    def _create_layout(self) -> QVBoxLayout:
        """Crea y arma los layouts de la pestaña."""
        choose_row = QHBoxLayout()
        choose_row.addWidget(self._choose_button)
        choose_row.addWidget(self._file_label, 1)

        profile_row = QHBoxLayout()
        profile_row.addWidget(self._profile_combo)
        profile_row.addWidget(self._process_button)
        profile_row.addWidget(self._cancel_button)
        profile_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(choose_row)
        layout.addLayout(profile_row)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table_view, 1)
        layout.addWidget(self._refresh_button)
        return layout

    def _connect_signals(self) -> None:
        """Conecta las señales de los controles a los slots de la pestaña."""
        self._choose_button.clicked.connect(self._on_choose_clicked)
        self._process_button.clicked.connect(self._on_process_clicked)
        self._cancel_button.clicked.connect(self.cancel)
        self._refresh_button.clicked.connect(self.refresh_runs)

    def _on_choose_clicked(self) -> None:
        """Abre el diálogo de archivo y muestra el nombre del video elegido."""
        config = self._session.config
        directory = config.under_root(config.input.allowed_dirs[0])
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            VIDEO_DIALOG_CAPTION,
            str(directory),
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
        self._status_label.setText(
            f"frames {update.frames_processed}/{update.frames_decoded} "
            f"· avistamientos {update.sightings_saved}"
        )

    def _on_succeeded(self, result: RunResult) -> None:
        """Muestra el resumen final de la corrida exitosa."""
        stats = result.stats
        velocity = f"{stats.speed_factor:.2f}x" if stats.speed_factor is not None else NOT_AVAILABLE
        self._status_label.setText(
            f"run_id={result.run_id} frames={stats.frames_processed}/{stats.frames_decoded} "
            f"confirmadas={stats.sightings_confirmed} sin_verificar={stats.sightings_unverified} "
            f"sin_lectura={stats.tracks_without_reading} velocidad={velocity}"
        )

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
