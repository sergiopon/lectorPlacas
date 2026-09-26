# 009 - Aplicación: muestreo de frames por tiempo

## Objetivo
Implementar `TimeBasedFrameSampler`, que decide qué frames procesar según su timestamp y el
`target_fps` del perfil (correcto con fps variable).

## Depende de
001, 005.

## Archivos rectores aplicables
- ADR-006 (regla de muestreo). ARQUITECTURA.md §2 (application), §6.

## Archivos a crear/modificar
- `src/lector_placas/application/frame_sampler.py`
- `tests/unit/application/test_frame_sampler.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
```python
# de application/ports.py (spec 005)
class FrameSampler(Protocol):
    def should_process(self, timestamp_ms: int) -> bool: ...
    def reset(self) -> None: ...
# de domain/errors.py
class ConfigurationError(LectorPlacasError): ...
class InvalidEntityError(DomainError): ...
```
```python
# application/frame_sampler.py — a implementar
TOLERANCE_MS: Final[float] = 1.0

class TimeBasedFrameSampler:
    def __init__(self, target_fps: float) -> None: ...
    def should_process(self, timestamp_ms: int) -> bool: ...
    def reset(self) -> None: ...
```

## Comportamiento esperado
1. `__init__`: si `target_fps` no es finito o `<= 0` → `ConfigurationError("target_fps debe ser > 0")`.
   `interval_ms = 1000.0 / target_fps`; `_last_ms: int | None = None`.
2. `should_process(timestamp_ms)`:
   - `timestamp_ms < 0` → `InvalidEntityError("timestamp_ms debe ser >= 0")`.
   - Si `_last_ms is None`, o `timestamp_ms < _last_ms` (salto hacia atrás), o
     `timestamp_ms - _last_ms >= interval_ms - TOLERANCE_MS`: `_last_ms = timestamp_ms` y devuelve `True`.
   - En otro caso devuelve `False`.
3. `reset()`: `_last_ms = None`.

## Casos borde y manejo de errores
- Con `target_fps` mayor que el fps del video se procesan todos los frames.

## Tests de aceptación
```python
# tests/unit/application/test_frame_sampler.py
from __future__ import annotations

import math

import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError


def run(sampler: TimeBasedFrameSampler, stamps: list[int]) -> list[int]:
    return [t for t in stamps if sampler.should_process(t)]


def test_constant_30fps_video_sampled_at_10fps() -> None:
    stamps = [round(i * 1000 / 30) for i in range(31)]
    assert run(TimeBasedFrameSampler(10), stamps) == [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]


def test_tolerance_accepts_99ms_at_10fps() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 33, 66, 99, 133, 199]) == [0, 99, 199]


def test_variable_frame_rate() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 150, 151, 260, 262, 400]) == [0, 150, 260, 400]


def test_high_target_processes_everything() -> None:
    stamps = [0, 40, 80, 120]
    assert run(TimeBasedFrameSampler(60), stamps) == stamps


def test_backwards_jump_is_processed() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 500, 100, 150, 250]) == [0, 500, 100, 250]


def test_reset() -> None:
    sampler = TimeBasedFrameSampler(1)
    assert sampler.should_process(0)
    assert not sampler.should_process(10)
    sampler.reset()
    assert sampler.should_process(10)


@pytest.mark.parametrize("fps", [0, -5, math.inf, math.nan])
def test_invalid_fps(fps: float) -> None:
    with pytest.raises(ConfigurationError):
        TimeBasedFrameSampler(fps)


def test_negative_timestamp() -> None:
    with pytest.raises(InvalidEntityError):
        TimeBasedFrameSampler(10).should_process(-1)
```

## Fuera de alcance
Decodificación (spec 010).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
