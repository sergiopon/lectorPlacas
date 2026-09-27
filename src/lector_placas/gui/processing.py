"""Hilo de procesamiento de la GUI: reporter de progreso y worker sobre `QThread` (ADR-015)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, Signal

from lector_placas.application.ports import CropStore, KeyProvider, PlateRepository, ProgressUpdate
from lector_placas.application.process_video import ProcessVideo
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError, ProcessingCancelledError
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.config import AppConfig
from lector_placas.infrastructure.input_validation import sha256_file

REPORT_MIN_INTERVAL_S: Final[float] = 0.1
GENERIC_ERROR_MESSAGE: Final[str] = "error inesperado; revise logs/lector.log"

logger = logging.getLogger(__name__)


class QtProgressReporter:
    """Comunica el avance del pipeline a una señal Qt y guarda la petición de cancelación."""

    def __init__(
        self,
        emit: Callable[[ProgressUpdate], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Guarda el emisor, el reloj y el estado de cancelación.

        Args:
            emit: callable que envía un `ProgressUpdate` (típicamente `Signal.emit`).
            clock: fuente de tiempo monótona en segundos; por defecto `time.monotonic`.
        """
        self._emit = emit
        self._clock = clock
        self._cancel = threading.Event()
        self._last_sent: float | None = None

    def report(self, update: ProgressUpdate) -> None:
        """Emite `update` si pasó al menos `REPORT_MIN_INTERVAL_S`; el primero siempre se envía."""
        now = self._clock()
        if self._last_sent is None or now - self._last_sent >= REPORT_MIN_INTERVAL_S:
            self._last_sent = now
            self._emit(update)

    def cancel_requested(self) -> bool:
        """Indica si el operador pidió cancelar el procesamiento."""
        return self._cancel.is_set()

    def request_cancel(self) -> None:
        """Activa la petición de cancelación."""
        self._cancel.set()


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    """Solicitud de procesamiento: video ya validado y nombre del perfil."""

    video: Path
    profile_name: str


class ProcessingWorker(QObject):
    """Ejecuta `ProcessVideo` en el hilo de un `QThread` con su propia conexión a la BD."""

    progress = Signal(object)
    succeeded = Signal(object)
    cancelled = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config: AppConfig, keys: KeyProvider, request: ProcessingRequest) -> None:
        """Guarda la configuración, la clave y la solicitud; prepara la cancelación.

        Args:
            config: configuración de la aplicación.
            keys: proveedor de la clave maestra, ya leída antes de bloquear la red.
            request: video a procesar y perfil a usar.
        """
        super().__init__()
        self._config = config
        self._keys = keys
        self._request = request
        self._cancel = threading.Event()
        self._reporter: QtProgressReporter | None = None
        self._repository: PlateRepository | None = None

    def run(self) -> None:
        """Ejecuta el procesamiento completo en el hilo del `QThread` (conectado a `started`)."""
        logger.info("procesamiento gui inicio perfil=%s", self._request.profile_name)
        try:
            outcome = self._run_protected()
        finally:
            self._cleanup_repository()
        logger.info("procesamiento gui fin resultado=%s", outcome)
        self.finished.emit()

    def _run_protected(self) -> str:
        """Ejecuta el procesamiento protegido con manejo de errores."""
        try:
            repository, crop_store = self._open_repository()
            use_case = composition.build_process_video(
                self._config, self._request.profile_name, repository, crop_store, SystemClock()
            )
            return self._execute_and_report(use_case)
        except ProcessingCancelledError:
            self.cancelled.emit()
            return "cancelado"
        except LectorPlacasError as error:
            self.failed.emit(str(error))
            return "error"
        except Exception:  # permitido en trabajo del hilo, ARQUITECTURA §6
            logger.exception("procesamiento gui error inesperado")
            self.failed.emit(GENERIC_ERROR_MESSAGE)
            return "error"

    def _cleanup_repository(self) -> None:
        """Cierra el repositorio del hilo si llegó a abrirse."""
        repository = self._repository
        if repository is not None:
            repository.close()

    def _open_repository(self) -> tuple[PlateRepository, CropStore]:
        """Construye el repositorio y el almacén de recortes en el hilo del worker.

        Guarda el repositorio en `self._repository` para que `run()` lo cierre siempre en su
        bloque `finally`, incluso si `build_crop_store` o el resto del procesamiento falla.
        """
        repository = composition.build_repository(self._config, self._keys)
        self._repository = repository
        crop_store = composition.build_crop_store(self._config, self._keys)
        return repository, crop_store

    def _execute_and_report(self, use_case: ProcessVideo) -> str:
        """Ejecuta el caso de uso y emite el resultado."""
        sha = sha256_file(self._request.video)
        reporter = self._create_reporter()
        if self._cancel.is_set():
            reporter.request_cancel()
        result = use_case.execute(self._request.video, sha, reporter)
        self.succeeded.emit(result)
        return "ok"

    def _create_reporter(self) -> QtProgressReporter:
        """Crea el reporter de progreso para el caso de uso."""
        reporter = QtProgressReporter(self.progress.emit)
        self._reporter = reporter
        return reporter

    def request_cancel(self) -> None:
        """Pide cancelar el procesamiento en curso, si lo hay."""
        self._cancel.set()
        reporter = self._reporter
        if reporter is not None:
            reporter.request_cancel()
