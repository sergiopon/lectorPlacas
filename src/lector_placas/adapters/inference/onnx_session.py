"""Creación uniforme de sesiones de ONNX Runtime (CUDA o CPU)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Final, Literal, Protocol, TypeAlias, cast

import numpy.typing as npt
import onnxruntime
from onnxruntime.capi.onnxruntime_pybind11_state import (
    EngineError,
    EPFail,
    Fail,
    InvalidArgument,
    InvalidGraph,
    InvalidProtobuf,
    NoModel,
    NoSuchFile,
    NotImplemented,
    RuntimeException,
)

from lector_placas.domain.errors import ModelLoadError

ExecutionProvider: TypeAlias = Literal["cuda", "cpu"]  # noqa: UP040

ORT_ERRORS: Final[tuple[type[BaseException], ...]] = (
    RuntimeError,
    OSError,
    ValueError,
    Fail,
    InvalidArgument,
    NoSuchFile,
    NoModel,
    EngineError,
    RuntimeException,
    InvalidProtobuf,
    NotImplemented,
    InvalidGraph,
    EPFail,
)


class InferenceSessionLike(Protocol):
    """Subconjunto de `onnxruntime.InferenceSession` usado por el proyecto."""

    def run(
        self,
        output_names: list[str] | None,
        input_feed: dict[str, npt.NDArray[Any]],
    ) -> list[npt.NDArray[Any]]:
        """Ejecuta la sesión y devuelve las salidas solicitadas."""
        ...


@functools.cache
def _preload_cuda_libraries() -> None:
    """Carga las bibliotecas CUDA/cuDNN de los paquetes `nvidia-*` instalados."""
    onnxruntime.preload_dlls(directory="")


def providers_for(execution_provider: ExecutionProvider) -> list[str]:
    """Devuelve la lista de proveedores de ejecución de ONNX Runtime."""
    if execution_provider == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def create_session(model_path: Path, execution_provider: ExecutionProvider) -> InferenceSessionLike:
    """Crea una sesión de inferencia de ONNX Runtime para el modelo dado.

    Args:
        model_path: ruta al modelo `.onnx` ya verificado por el registro de modelos.
        execution_provider: `"cuda"` o `"cpu"`.

    Returns:
        Sesión de inferencia lista para ejecutar.

    Raises:
        ModelLoadError: si CUDA no está disponible (cuando se pide `"cuda"`) o si la carga falla.
    """
    if execution_provider == "cuda":
        _preload_cuda_libraries()
        if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
            raise ModelLoadError("CUDA no disponible en ONNX Runtime")
    try:
        session = onnxruntime.InferenceSession(
            str(model_path), providers=providers_for(execution_provider)
        )
        return cast(InferenceSessionLike, session)
    except ORT_ERRORS as e:
        raise ModelLoadError(f"no se pudo cargar el modelo: {model_path.name}") from e
