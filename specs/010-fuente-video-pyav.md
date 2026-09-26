# 010 - Adaptador: fuente de video con PyAV

## Objetivo
Implementar `PyAVVideoSourceFactory` / `PyAVVideoSource`: abrir un video, verificar que decodifica y
entregar frames BGR derechos (rotación aplicada) con timestamp relativo en ms basado en PTS.

## Depende de
001, 005.

## Archivos rectores aplicables
- ADR-010 (PTS, rotación con `np.rot90`), requisitos RF-01, RF-23.
- reglas-seguridad.md SEG-12 (el archivo debe decodificar), SEG-26 (mensajes sin rutas absolutas).
- ARQUITECTURA.md §6 (envolver `av.error.FFmpegError` en `VideoSourceError`).

## Archivos a crear/modificar
- `src/lector_placas/adapters/video/pyav_source.py`
- `tests/integration/test_pyav_source.py`
- `tests/fixtures/synthetic_video.py`

## Dependencias externas
av==18.1.0, numpy==2.5.3 (ya instalados).

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
ImageBGR: TypeAlias = npt.NDArray[np.uint8]
@dataclass(frozen=True, slots=True, eq=False)
class Frame: index: int; timestamp_ms: int; image: ImageBGR
@dataclass(frozen=True, slots=True)
class VideoInfo: width: int; height: int; rotation_deg: int; duration_ms: int | None; average_fps: float | None; codec: str
class VideoSource(Protocol):
    def info(self) -> VideoInfo: ...
    def frames(self) -> Iterator[Frame]: ...
    def close(self) -> None: ...
class VideoSourceFactory(Protocol):
    def open(self, path: Path) -> VideoSource: ...
# de domain/errors.py
class VideoSourceError(LectorPlacasError): ...
```
```python
# adapters/video/pyav_source.py — a implementar
class PyAVVideoSourceFactory:
    def open(self, path: Path) -> PyAVVideoSource: ...

class PyAVVideoSource:
    def __init__(self, container: av.container.InputContainer, name: str) -> None: ...
    def info(self) -> VideoInfo: ...
    def frames(self) -> Iterator[Frame]: ...
    def close(self) -> None: ...

def rotation_steps(rotation: int) -> int: ...     # round(rotation / 90) % 4
```

## Comportamiento esperado
1. `rotation_steps(rotation)` = `round(rotation / 90) % 4` (p. ej. 90→1, -90→3, 180→2, -180→2, 0→0).
2. `PyAVVideoSourceFactory.open(path)`:
   - `container = av.open(str(path), mode="r")`; `av.error.FFmpegError` u `OSError` → `VideoSourceError("no se pudo abrir el video: <path.name>") from e`.
   - Si `not container.streams.video` → cerrar y `VideoSourceError("el archivo no contiene video: <path.name>")`.
   - Devuelve `PyAVVideoSource(container, path.name)`.
3. `PyAVVideoSource.__init__`: `stream = container.streams.video[0]`; `stream.thread_type = "AUTO"`;
   crea el iterador `container.decode(stream)` y **decodifica el primer frame** (lo guarda para `frames()`).
   Si no hay ninguno o falla la decodificación → cierra y `VideoSourceError("el video no tiene frames decodificables: <name>")`.
   Con el primer frame calcula: `steps = rotation_steps(first.rotation)`, `first_pts = first.pts` (si `None`, `VideoSourceError`).
4. `info()`: `w, h = first.width, first.height`; si `steps` es impar se intercambian.
   `rotation_deg = steps * 90`; `duration_ms = container.duration // 1000` si `container.duration` no es `None` (unidades de µs), si no `None`;
   `average_fps = float(stream.average_rate)` si existe y es > 0, si no `None`; `codec = stream.codec_context.name`.
5. `frames()` (generador; solo se puede consumir una vez, una segunda llamada → `VideoSourceError("frames() ya fue consumido")`):
   - Recorre el primer frame guardado y luego el resto del iterador.
   - Frames con `pts is None` se omiten con `logger.warning("frame sin pts omitido")`.
   - `time_base = frame.time_base or stream.time_base`; `timestamp_ms = round((frame.pts - first_pts) * time_base * 1000)` (aritmética `Fraction`).
   - Si `timestamp_ms < 0` o menor que el último emitido, se omite con `logger.debug`.
   - `image = frame.to_ndarray(format="bgr24")`; si `steps != 0`: `image = np.ascontiguousarray(np.rot90(image, k=steps))`.
   - Emite `Frame(index, timestamp_ms, image)` con `index` = contador de frames emitidos (desde 0).
   - `av.error.FFmpegError` durante la decodificación → `VideoSourceError("error decodificando el video: <name>") from e`.
6. `close()`: idempotente; llama `container.close()` una sola vez.

## Casos borde y manejo de errores
- Archivo de texto con extensión `.mp4` → `VideoSourceError` en `open`.
- Logger del módulo: `logging.getLogger(__name__)`; nunca registrar la ruta absoluta.

## Tests de aceptación
```python
# tests/fixtures/synthetic_video.py
from __future__ import annotations

from pathlib import Path

import av
import numpy as np


def synthetic_frame(index: int, width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:8, :8] = 255                     # marca blanca arriba a la izquierda
    image[height - 4:, :, 2] = (index * 20) % 256
    return image


def write_video(path: Path, frames: int = 10, fps: int = 10, width: int = 64, height: int = 48,
                rotation: float | None = None) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        if rotation is not None:
            stream.set_display_rotation(rotation)
        for index in range(frames):
            frame = av.VideoFrame.from_ndarray(synthetic_frame(index, width, height), format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path
```
```python
# tests/integration/test_pyav_source.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.adapters.video.pyav_source import PyAVVideoSourceFactory, rotation_steps
from lector_placas.domain.errors import VideoSourceError
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("rotation,steps", [(0, 0), (90, 1), (-90, 3), (180, 2), (-180, 2), (270, 3)])
def test_rotation_steps(rotation: int, steps: int) -> None:
    assert rotation_steps(rotation) == steps


def test_reads_frames_with_pts_timestamps(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=10, fps=10))
    try:
        info = source.info()
        frames = list(source.frames())
    finally:
        source.close()
    assert (info.width, info.height, info.rotation_deg, info.codec) == (64, 48, 0, "mpeg4")
    assert [f.timestamp_ms for f in frames] == [i * 100 for i in range(10)]
    assert [f.index for f in frames] == list(range(10))
    assert frames[0].image.shape == (48, 64, 3)
    assert frames[0].image[:6, :6].mean() > 200


def test_applies_display_rotation(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "r.mp4", rotation=90))
    try:
        info = source.info()
        first = next(iter(source.frames()))
    finally:
        source.close()
    assert info.rotation_deg == 90
    assert (info.width, info.height) == (48, 64)
    assert first.image.shape == (64, 48, 3)
    assert first.image.flags["C_CONTIGUOUS"]
    assert first.image[-6:, :6].mean() > 200      # np.rot90 lleva arriba-izquierda a abajo-izquierda


def test_frames_can_only_be_consumed_once(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=2))
    list(source.frames())
    with pytest.raises(VideoSourceError):
        list(source.frames())
    source.close()
    source.close()


def test_rejects_non_video(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"esto no es un video")
    with pytest.raises(VideoSourceError):
        PyAVVideoSourceFactory().open(fake)


def test_images_are_uint8_bgr(tmp_path: Path) -> None:
    source = PyAVVideoSourceFactory().open(write_video(tmp_path / "v.mp4", frames=1))
    frame = next(iter(source.frames()))
    source.close()
    assert frame.image.dtype == np.uint8
```

## Fuera de alcance
Validación de ruta/extensión/tamaño (spec 007); muestreo (spec 009).

## Definition of Done
- [ ] `uv run pytest -m integration tests/integration/test_pyav_source.py` en verde. **Si `test_applies_display_rotation` falla, detente y reporta la salida (ADR-010 exige revisión); no cambies la convención de rotación.**
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
