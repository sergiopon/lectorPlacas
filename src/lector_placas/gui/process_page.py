"""Página "Procesar": flujo guiado de elegir video, procesar y revisar (spec 049, ADR-015)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from lector_placas.application.ports import ProgressUpdate, RunRecord, RunStatus, SightingQuery
from lector_placas.application.process_video import RunResult
from lector_placas.cli import composition
from lector_placas.domain.entities import SightingRecord
from lector_placas.domain.errors import (
    CropNotFoundError,
    CropStoreError,
    EncryptionError,
    LectorPlacasError,
    RepositoryError,
)
from lector_placas.gui.images import bgr_to_pixmap
from lector_placas.gui.plate_card import CROP_BOX
from lector_placas.gui.process_views import Crops, DoneView, IdleView, RunningView
from lector_placas.gui.processing import ProcessingRequest, ProcessingWorker
from lector_placas.gui.session import GuiSession

LIVE_REFRESH_S: Final[float] = 1.0
LIVE_PAGE_SIZE: Final[int] = 200
RUNS_PROBE: Final[int] = 1

RefreshTarget = RunningView | DoneView


def _monotonic() -> float:
    """Reloj monótono en segundos, sustituible en los tests."""
    return time.monotonic()


class ProcessPage(QWidget):
    """Flujo guiado de procesar un video: inicio, progreso en vivo y resumen."""

    busy_changed = Signal(bool)
    review_requested = Signal(object)
    run_finished = Signal()

    def __init__(self, session: GuiSession) -> None:
        """Crea la página con sus tres vistas y el trabajo en segundo plano."""
        super().__init__()
        self._session = session
        self._video: Path | None = None
        self._busy = False
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._started_at = 0.0
        self._last_refresh: float | None = None
        self._last_saved = 0
        self._run_id: int | None = None
        self._done_run_id: int | None = None
        self._idle = IdleView(session.config, self)
        self._running = RunningView(self)
        self._done = DoneView(self)
        self._stack = QStackedWidget(self)
        for view in (self._idle, self._running, self._done):
            self._stack.addWidget(view)
        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)
        _connect(self)

    def choose_video(self, path: Path) -> None:
        """Valida `path` y, si sirve, pasa al paso "listo para empezar"."""
        try:
            video = composition.validated_video(self._session.config, path)
        except LectorPlacasError as error:
            self._video = None
            self._idle.select_video(None)
            self._idle.show_error(str(error))
            return
        self._video = video
        self._idle.select_video(video)

    def start(self) -> None:
        """Arranca el procesamiento del video elegido en un `QThread`."""
        if self.is_busy() or self._video is None:
            return
        thread = QThread(self)
        request = ProcessingRequest(self._video, self._idle.selected_profile())
        worker = ProcessingWorker(self._session.config, self._session.keys, request)
        _wire_worker(self, worker, thread)
        self._thread, self._worker = thread, worker
        self._started_at = _monotonic()
        self._last_refresh, self._last_saved = None, 0
        self._running.start(self._video.name)
        self._stack.setCurrentWidget(self._running)
        thread.start()
        self._set_busy(True)

    def cancel(self) -> None:
        """Pide cancelar el procesamiento y deja el botón en "Cancelando…"."""
        if self._worker is not None:
            self._worker.request_cancel()
        self._running.set_cancelling()

    def is_busy(self) -> bool:
        """Indica si hay un procesamiento en curso."""
        return self._busy

    def wait_for_worker(self) -> None:
        """Bloquea hasta que el hilo de procesamiento termine, si hay uno."""
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.wait()

    def _on_progress(self, update: ProgressUpdate) -> None:
        """Actualiza la vista en curso y refresca la galería si hay placas nuevas."""
        self._running.set_progress(update, _monotonic() - self._started_at)
        self._maybe_refresh(update.sightings_saved)

    def _maybe_refresh(self, saved: int) -> None:
        """Refresca la galería en vivo si aumentaron las placas y venció el intervalo."""
        if saved <= self._last_saved:
            return
        now = _monotonic()
        if self._last_refresh is not None and now - self._last_refresh < LIVE_REFRESH_S:
            return
        self._last_saved, self._last_refresh = saved, now
        run_id = self._running_run_id()
        if run_id is not None:
            _show_grid(self._running, self._session, run_id)

    def _running_run_id(self) -> int | None:
        """Devuelve el `run_id` de la corrida en curso y lo recuerda, si la hay."""
        runs = _list_runs(self._session)
        if not runs or runs[0].status is not RunStatus.RUNNING:
            return None
        self._run_id = runs[0].run_id
        return self._run_id

    def _on_succeeded(self, result: RunResult) -> None:
        """Muestra el resumen de éxito y refresca la galería de la corrida."""
        self._run_id = result.run_id
        self._done_run_id = result.run_id
        self._done.show_success(result)
        self._stack.setCurrentWidget(self._done)
        self._refresh_done()

    def _on_cancelled(self) -> None:
        """Muestra el resumen de cancelación con lo que se alcanzó a guardar."""
        self._done_run_id = self._run_id
        self._done.show_cancelled()
        self._stack.setCurrentWidget(self._done)
        self._refresh_done()

    def _on_failed(self, message: str) -> None:
        """Vuelve al inicio con el error en rojo, conservando el video elegido."""
        self._idle.show_error(message)
        self._stack.setCurrentWidget(self._idle)

    def _on_finished(self) -> None:
        """Restablece el estado ocupado y avisa del fin del hilo."""
        self._set_busy(False)
        self.run_finished.emit()

    def _refresh_done(self) -> None:
        """Refresca la galería del resumen con los avistamientos de la corrida."""
        run_id = self._run_id if self._run_id is not None else _recent_run_id(self._session)
        if run_id is not None:
            _show_grid(self._done, self._session, run_id)

    def _set_busy(self, busy: bool) -> None:
        """Actualiza el estado ocupado y lo emite."""
        self._busy = busy
        self.busy_changed.emit(busy)

    def _emit_review(self) -> None:
        """Emite la petición de revisar lo pendiente de la corrida terminada."""
        self.review_requested.emit(self._done_run_id)

    def _clear_video(self) -> None:
        """Quita el video elegido y vuelve al paso de inicio."""
        self._video = None
        self._idle.select_video(None)


def _restart(page: ProcessPage) -> None:
    """Vuelve al inicio sin video para procesar otro archivo."""
    page._run_id = None
    page._done_run_id = None
    page._clear_video()
    page._stack.setCurrentWidget(page._idle)


def _connect(page: ProcessPage) -> None:
    """Conecta las señales de las vistas con los slots de la página."""
    page._idle.video_chosen.connect(page.choose_video)
    page._idle.start_requested.connect(page.start)
    page._idle.change_requested.connect(page._clear_video)
    page._running.cancel_requested.connect(page.cancel)
    page._done.review_requested.connect(page._emit_review)
    page._done.restart_requested.connect(lambda: _restart(page))


def _wire_worker(page: ProcessPage, worker: ProcessingWorker, thread: QThread) -> None:
    """Conecta las señales del worker a los slots de `page`.

    `quit()` va con conexión directa para que corra en el hilo del worker: si fuera
    encolada al hilo de la GUI, `wait_for_worker()` (que bloquea) nunca la procesaría.
    """
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
    worker.progress.connect(page._on_progress)
    worker.succeeded.connect(page._on_succeeded)
    worker.cancelled.connect(page._on_cancelled)
    worker.failed.connect(page._on_failed)
    worker.finished.connect(page._on_finished)


def _recent_run_id(session: GuiSession) -> int | None:
    """Devuelve el `run_id` de la corrida más reciente, o `None` si no hay ninguna."""
    runs = _list_runs(session)
    return runs[0].run_id if runs else None


def _list_runs(session: GuiSession) -> list[RunRecord]:
    """Lista la corrida más reciente; un error del repositorio devuelve una lista vacía."""
    try:
        return session.browser.list_runs(RUNS_PROBE, 0)
    except RepositoryError:
        return []


def _show_grid(view: RefreshTarget, session: GuiSession, run_id: int) -> None:
    """Carga en la galería de `view` los avistamientos de `run_id`."""
    try:
        records = session.browser.search_sightings(SightingQuery(run_id=run_id), LIVE_PAGE_SIZE, 0)
    except RepositoryError:
        return
    view.set_records(records, _load_crops(session, records))


def _load_crops(session: GuiSession, records: Sequence[SightingRecord]) -> Crops:
    """Carga los recortes de `records` como `QPixmap`, sin lanzar por los ilegibles."""
    return {record.sighting_id: _load_crop(session, record) for record in records}


def _load_crop(session: GuiSession, record: SightingRecord) -> QPixmap | None:
    """Carga el recorte de `record`, o `None` si ya no está o no se puede leer."""
    if record.crop_ref is None:
        return None
    try:
        return bgr_to_pixmap(session.crop_store.load(record.crop_ref), *CROP_BOX)
    except (CropNotFoundError, CropStoreError, EncryptionError):
        return None
