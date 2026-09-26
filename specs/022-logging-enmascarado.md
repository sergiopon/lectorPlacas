# 022 - Infraestructura: logging con placas enmascaradas

## Objetivo
Configurar el logging del proceso (archivo 0600 + stderr) con redacción de cualquier patrón de placa
en mensajes y trazas.

## Depende de
004 (`mask_plate`), 007.

## Archivos rectores aplicables
- docs/02-contratos.md §8 (patrón y formato literales). reglas-seguridad.md SEG-04, SEG-05.

## Archivos a crear/modificar
- `src/lector_placas/infrastructure/logging_setup.py`
- `tests/unit/infrastructure/test_logging_setup.py`

## Dependencias externas
Ninguna (stdlib `logging`).

## Interfaces y tipos involucrados
```python
# de domain/privacy.py (spec 004)
def mask_plate(text: str) -> str: ...   # "ABC123" -> "A****3"
# de infrastructure/paths.py (spec 007)
def ensure_private_dir(path: Path) -> Path: ...
# de domain/errors.py
class ConfigurationError(LectorPlacasError): ...
```
```python
# infrastructure/logging_setup.py — a implementar
PLATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{3}[0-9]{2}[A-Z0-9]?|[0-9]{3}[A-Z]{3}|[A-Z]{2}[0-9]{4}|[RS][0-9]{5}|T[0-9]{4})(?![A-Z0-9])")
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"
HANDLER_MARK: Final[str] = "_lector_placas_handler"

def redact_plates(text: str) -> str: ...
class PlateRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool: ...
class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str: ...
def configure_logging(level: str, log_file: Path) -> None: ...
```

## Comportamiento esperado
1. `redact_plates(text)` = `PLATE_PATTERN.sub(lambda m: mask_plate(m.group(0)), text)`.
2. `PlateRedactionFilter.filter`: `message = record.getMessage()`; si `redact_plates(message) != message`,
   asigna `record.msg = redact_plates(message)` y `record.args = None`. Siempre devuelve `True`.
3. `RedactingFormatter.format` = `redact_plates(super().format(record))` (cubre trazas de excepción).
4. `configure_logging(level, log_file)`:
   - `level` ∉ {"DEBUG", "INFO", "WARNING", "ERROR"} → `ConfigurationError`.
   - `ensure_private_dir(log_file.parent)`; si el archivo no existe se crea con `os.open(..., os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)`; `os.chmod(log_file, 0o600)`.
   - En el logger raíz: elimina los handlers que tengan el atributo `HANDLER_MARK` (idempotencia), fija el nivel,
     añade `logging.FileHandler(log_file, encoding="utf-8")` y `logging.StreamHandler(sys.stderr)`, cada uno con
     `RedactingFormatter(LOG_FORMAT)`, `PlateRedactionFilter()` y `setattr(handler, HANDLER_MARK, True)`.

## Casos borde y manejo de errores
- Texto sin placas no cambia. Minúsculas no se redactan (las placas del sistema están en mayúsculas).

## Tests de aceptación
```python
# tests/unit/infrastructure/test_logging_setup.py
from __future__ import annotations

import logging
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from lector_placas.domain.errors import ConfigurationError
from lector_placas.infrastructure.logging_setup import HANDLER_MARK, configure_logging, redact_plates


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARK, False):
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.mark.parametrize("text,expected", [
    ("placa ABC123 leída", "placa A****3 leída"),
    ("moto XYZ98K", "moto X****K"),
    ("motocarro 123ABC", "motocarro 1****C"),
    ("diplomática CD1234", "diplomática C****4"),
    ("remolque R12345", "remolque R****5"),
    ("temporal T1234", "temporal T***4"),
    ("run_id=12 frames=300", "run_id=12 frames=300"),
    ("abc123", "abc123"),
    ("XABC1234", "XABC1234"),
])
def test_redact_plates(text: str, expected: str) -> None:
    assert redact_plates(text) == expected


def test_configure_logging_writes_redacted_private_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "lector.log"
    configure_logging("INFO", log_file)
    configure_logging("INFO", log_file)
    logger = logging.getLogger("lector_placas.test")
    logger.info("placa %s detectada", "ABC123")
    try:
        raise ValueError("fallo con XYZ98K")
    except ValueError:
        logger.exception("error")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "ABC123" not in content and "XYZ98K" not in content
    assert "A****3" in content and "X****K" in content
    assert content.count("placa A****3 detectada") == 1
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(log_file.parent.stat().st_mode) == 0o700


def test_invalid_level() -> None:
    with pytest.raises(ConfigurationError):
        configure_logging("VERBOSE", Path("/tmp/no-importa.log"))
```

## Fuera de alcance
Qué eventos se registran (cada spec lo define).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
