"""Trabajos de procesamiento de la web: un hilo por corrida, con avance y cancelación."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from lector_placas.application.ports import KeyProvider, ProgressReporter, ProgressUpdate
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError, ProcessingCancelledError
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.config import AppConfig
from lector_placas.infrastructure.input_validation import sha256_file

logger = logging.getLogger(__name__)

type JobRunner = Callable[[Path, str, ProgressReporter], int]
type JobState = Literal["running", "completed", "cancelled", "failed"]
GENERIC_ERROR_MESSAGE: Final[str] = "error inesperado; revise logs/lector.log"


class JobBusyError(LectorPlacasError):
    """Ya hay un procesamiento en curso."""


class JobNotFoundError(LectorPlacasError):
    """El trabajo indicado no existe."""


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Copia inmutable del estado de un trabajo."""

    job_id: str
    state: JobState
    run_id: int | None
    progress: ProgressUpdate | None
    message: str | None


class JobReporter:
    """Reporter de progreso seguro entre hilos."""

    def __init__(self) -> None:
        """Crea el reporter sin avance y sin cancelación."""
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._latest: ProgressUpdate | None = None

    def report(self, update: ProgressUpdate) -> None:
        """Guarda el último avance."""
        with self._lock:
            self._latest = update

    def cancel_requested(self) -> bool:
        """Indica si se pidió cancelar."""
        return self._cancel.is_set()

    def request_cancel(self) -> None:
        """Pide cancelar el trabajo."""
        self._cancel.set()

    def latest(self) -> ProgressUpdate | None:
        """Devuelve el último avance guardado."""
        with self._lock:
            return self._latest


@dataclass(slots=True)
class _Job:
    """Estado mutable interno de un trabajo."""

    reporter: JobReporter
    state: JobState = "running"
    run_id: int | None = None
    message: str | None = None


class JobManager:
    """Gestiona un único procesamiento a la vez en un hilo."""

    def __init__(self, runner: JobRunner) -> None:
        """Crea el gestor.

        Args:
            runner: función que procesa el video y devuelve el `run_id`.
        """
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}

    def start(self, video: Path, profile: str) -> str:
        """Lanza un trabajo en un hilo.

        Args:
            video: video ya validado.
            profile: nombre del perfil.

        Returns:
            El identificador del trabajo.

        Raises:
            JobBusyError: si ya hay un trabajo en ejecución.
        """
        with self._lock:
            if any(job.state == "running" for job in self._jobs.values()):
                raise JobBusyError("ya hay un procesamiento en curso")
            job_id = uuid.uuid4().hex
            job = _Job(JobReporter())
            self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._work,
            args=(job, video, profile),
            name=f"lector-job-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return job_id

    def _finish(self, job: _Job, state: JobState, run_id: int | None, message: str | None) -> None:
        """Fija el estado final del trabajo bajo el cerrojo."""
        with self._lock:
            job.state = state
            job.run_id = run_id
            job.message = message

    def _work(self, job: _Job, video: Path, profile: str) -> None:
        """Cuerpo del hilo de trabajo."""
        try:
            run_id = self._runner(video, profile, job.reporter)
            self._finish(job, "completed", run_id, None)
        except ProcessingCancelledError:
            self._finish(job, "cancelled", None, "procesamiento cancelado")
        except LectorPlacasError as error:
            self._finish(job, "failed", None, str(error))
        except Exception:  # permitido en trabajo del hilo, ARQUITECTURA §6
            logger.exception("procesamiento web error inesperado")
            self._finish(job, "failed", None, GENERIC_ERROR_MESSAGE)

    def snapshot(self, job_id: str) -> JobSnapshot:
        """Devuelve una copia inmutable del estado del trabajo.

        Raises:
            JobNotFoundError: si el identificador no existe.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError("trabajo no encontrado")
            return JobSnapshot(job_id, job.state, job.run_id, job.reporter.latest(), job.message)

    def cancel(self, job_id: str) -> JobSnapshot:
        """Pide cancelar el trabajo y devuelve su estado.

        Raises:
            JobNotFoundError: si el identificador no existe.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError("trabajo no encontrado")
            job.reporter.request_cancel()
        return self.snapshot(job_id)


def default_runner(config: AppConfig, keys: KeyProvider) -> JobRunner:
    """Crea el runner real, con su propia conexión de base de datos en el hilo.

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra.

    Returns:
        La función que procesa un video y devuelve el `run_id`.
    """

    def run(video: Path, profile: str, reporter: ProgressReporter) -> int:
        repository = composition.build_repository(config, keys)
        try:
            crop_store = composition.build_crop_store(config, keys)
            use_case = composition.build_process_video(
                config, profile, repository, crop_store, SystemClock()
            )
            sha = sha256_file(video)
            return use_case.execute(video, sha, reporter).run_id
        finally:
            repository.close()

    return run
