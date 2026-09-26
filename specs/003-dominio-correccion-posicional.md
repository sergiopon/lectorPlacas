# 003 - Dominio: corrección posicional de confusiones OCR

## Objetivo
Implementar `ConfusionMap` y `correct_to_pattern`, que ajustan un texto OCR a un patrón `L`/`D`
sustituyendo caracteres confundibles (0↔O, 1↔I, 8↔B, 5↔S por defecto).

## Depende de
001.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 regla 1, §6. ADR-007 (paso 4). Requisito RF-11.
- docs/02-contratos.md §3.

## Archivos a crear/modificar
- `src/lector_placas/domain/ocr_correction.py`
- `tests/unit/domain/test_ocr_correction.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
```python
# de domain/entities.py (spec 001)
PLATE_TEXT_REGEX: Final[re.Pattern[str]]   # ^[A-Z0-9]{1,10}$
PATTERN_REGEX: Final[re.Pattern[str]]      # ^[LD]{1,10}$
# de domain/errors.py
class InvalidPlateTextError(DomainError): ...
class InvalidEntityError(DomainError): ...
class PlateFormatCatalogError(DomainError): ...
```
```python
# domain/ocr_correction.py — a implementar
@dataclass(frozen=True, slots=True)
class ConfusionMap:
    pairs: tuple[tuple[str, str], ...]
    @classmethod
    def default(cls) -> ConfusionMap: ...
    def to_digit(self, char: str) -> str: ...
    def to_letter(self, char: str) -> str: ...

def correct_to_pattern(text: str, pattern: str, confusions: ConfusionMap) -> str: ...
```

## Comportamiento esperado
1. `ConfusionMap.__post_init__`: cada par es `(letra, dígito)` con letra `^[A-Z]$` y dígito `^[0-9]$`;
   no hay letras repetidas ni dígitos repetidos entre pares. Violación → `InvalidEntityError("mapa de confusiones inválido: <detalle>")`.
   Un mapa vacío `()` es válido (no corrige nada).
2. `ConfusionMap.default()` devuelve `ConfusionMap((("O", "0"), ("I", "1"), ("B", "8"), ("S", "5")))`.
3. `to_digit(char)`: si `char` es una letra de algún par, devuelve su dígito; si no, devuelve `char` sin cambios.
   `to_letter(char)`: si `char` es un dígito de algún par, devuelve su letra; si no, `char`.
4. `correct_to_pattern(text, pattern, confusions)`:
   - `text` no cumple `PLATE_TEXT_REGEX` → `InvalidPlateTextError`.
   - `pattern` no cumple `PATTERN_REGEX` → `PlateFormatCatalogError`.
   - `len(text) != len(pattern)` → `InvalidPlateTextError("longitud de texto y patrón distintas")`.
   - Para cada posición: si el patrón dice `D` y el carácter es letra → `to_digit`; si dice `L` y el carácter es dígito → `to_letter`; en otro caso se deja igual.
   - Devuelve el texto resultante (puede seguir sin cumplir el patrón si el carácter no tiene par).

## Casos borde y manejo de errores
- Mensajes sin el texto de la placa (solo longitudes).

## Tests de aceptación
```python
# tests/unit/domain/test_ocr_correction.py
from __future__ import annotations

import pytest

from lector_placas.domain.errors import (
    InvalidEntityError, InvalidPlateTextError, PlateFormatCatalogError,
)
from lector_placas.domain.ocr_correction import ConfusionMap, correct_to_pattern

DEFAULT = ConfusionMap.default()


def test_default_pairs() -> None:
    assert DEFAULT.pairs == (("O", "0"), ("I", "1"), ("B", "8"), ("S", "5"))


def test_to_digit_and_to_letter() -> None:
    assert DEFAULT.to_digit("O") == "0"
    assert DEFAULT.to_digit("X") == "X"
    assert DEFAULT.to_letter("8") == "B"
    assert DEFAULT.to_letter("7") == "7"


@pytest.mark.parametrize("text,pattern,expected", [
    ("ABC12S", "LLLDDD", "ABC125"),
    ("ABC12S", "LLLDDL", "ABC12S"),
    ("ABC125", "LLLDDL", "ABC12S"),
    ("A8C1O3", "LLLDDD", "ABC103"),
    ("0BC123", "LLLDDD", "OBC123"),
    ("ABC12X", "LLLDDD", "ABC12X"),
    ("OI8BOS", "DDDLLL", "018BOS"),
])
def test_correct_to_pattern(text: str, pattern: str, expected: str) -> None:
    assert correct_to_pattern(text, pattern, DEFAULT) == expected


def test_empty_map_changes_nothing() -> None:
    assert correct_to_pattern("A8C1O3", "LLLDDD", ConfusionMap(())) == "A8C1O3"


def test_length_mismatch_raises() -> None:
    with pytest.raises(InvalidPlateTextError):
        correct_to_pattern("ABC12", "LLLDDD", DEFAULT)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(InvalidPlateTextError):
        correct_to_pattern("abc123", "LLLDDD", DEFAULT)
    with pytest.raises(PlateFormatCatalogError):
        correct_to_pattern("ABC123", "LLLXXX", DEFAULT)


@pytest.mark.parametrize("pairs", [
    (("O", "0"), ("O", "1")),
    (("O", "0"), ("Q", "0")),
    (("OO", "0"),),
    (("O", "A"),),
])
def test_confusion_map_rejects_invalid(pairs: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(InvalidEntityError):
        ConfusionMap(pairs)
```

## Fuera de alcance
Elección del patrón (lo hace la consolidación, spec 004).

## Definition of Done
- [ ] `uv run pytest tests/unit/domain tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
