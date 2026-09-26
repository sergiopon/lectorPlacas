"""M-06: monitor de VRAM pico basado en `nvidia-smi` (docs/04-evaluacion.md §3)."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from typing import Final

from lector_placas.domain.errors import EvaluationError

QUERY: Final[tuple[str, ...]] = (
    "nvidia-smi",
    "--query-gpu=memory.used",
    "--format=csv,noheader,nounits",
)
INTERVAL_MS: Final[int] = 200
UNAVAILABLE_MESSAGE: Final[str] = "nvidia-smi no disponible"
_WAIT_TIMEOUT_S: Final[int] = 5


def parse_mib(line: str) -> int | None:
    """Interpreta una línea de `nvidia-smi` como MiB.

    Args:
        line: línea de salida, posiblemente con espacios o `N/A`.

    Returns:
        El entero no negativo contenido en la línea, o `None` si no es un entero.
    """
    stripped = line.strip()
    if stripped.isdigit():
        return int(stripped)
    return None


class VramMonitor:
    """Muestrea el uso de VRAM en un hilo de fondo y calcula el pico sobre la línea base."""

    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        """Guarda las funciones de lanzamiento de subprocesos inyectables.

        Args:
            run: ejecuta un comando y espera a que termine.
            popen: lanza un comando sin esperar su fin.
        """
        self._run = run
        self._popen = popen
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._baseline: int | None = None
        self._samples: list[int] = []

    def __enter__(self) -> VramMonitor:
        """Mide la línea base y arranca el muestreo periódico.

        Raises:
            EvaluationError: si `nvidia-smi` no está disponible o no reporta enteros.
        """
        self._baseline = self._read_baseline()
        process = self._popen(  # argumentos fijos en lista, sin shell
            [*QUERY, "-lms", str(INTERVAL_MS)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._process = process
        thread = threading.Thread(target=self._sample, args=(process,), daemon=True)
        self._thread = thread
        thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Termina el subproceso de muestreo y espera al hilo lector."""
        if self._process is not None:
            self._process.terminate()
            self._process.wait(timeout=_WAIT_TIMEOUT_S)
        if self._thread is not None:
            self._thread.join(timeout=_WAIT_TIMEOUT_S)

    @property
    def peak_mib(self) -> int | None:
        """VRAM pico por encima de la línea base, o `None` si no hubo muestras."""
        if not self._samples:
            return None
        baseline = self._baseline if self._baseline is not None else 0
        return max(0, max(self._samples) - baseline)

    def _read_baseline(self) -> int:
        """Ejecuta `nvidia-smi` una vez y devuelve su primer entero de VRAM."""
        try:
            completed = self._run(  # argumentos fijos en lista, sin shell
                list(QUERY), capture_output=True, text=True, check=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise EvaluationError(UNAVAILABLE_MESSAGE) from error
        for line in completed.stdout.splitlines():
            value = parse_mib(line)
            if value is not None:
                return value
        raise EvaluationError(UNAVAILABLE_MESSAGE)

    def _sample(self, process: subprocess.Popen[str]) -> None:
        """Lee la salida periódica del subproceso y acumula las muestras válidas."""
        stream = process.stdout
        if stream is None:
            return
        for line in stream:
            value = parse_mib(line)
            if value is not None:
                self._samples.append(value)
