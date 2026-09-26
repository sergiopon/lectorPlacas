# 002 - Dominio: catálogo de formatos de placa

## Objetivo
Implementar `text_pattern` y `PlateFormatCatalog` para consultar los formatos de placa colombianos
(cargados desde configuración) por longitud, patrón y coincidencia de regex.

## Depende de
001.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 regla 1, §6.
- docs/02-contratos.md §3; docs/03-modelo-datos.md §4 (catálogo por defecto, reproducido en el fixture).
- Requisitos RF-12, RF-15, RF-19.

## Archivos a crear/modificar
- `src/lector_placas/domain/plate_formats.py`
- `tests/fixtures/plate_catalog.py` (fixture sintético reutilizado por specs 004, 006)
- `tests/unit/domain/test_plate_formats.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
```python
# de domain/entities.py (spec 001)
PLATE_TEXT_REGEX: Final[re.Pattern[str]]   # ^[A-Z0-9]{1,10}$
class VehicleType(StrEnum): CAR = "car"; MOTORCYCLE = "motorcycle"; BUS = "bus"; TRUCK = "truck"
@dataclass(frozen=True, slots=True)
class PlateFormat:
    format_id: str
    category: str
    pattern: str
    regex: str
    verified: bool
    vehicle_types: frozenset[VehicleType]
    source: str
    def matches(self, text: str) -> bool: ...
# de domain/errors.py
class InvalidPlateTextError(DomainError): ...
class PlateFormatCatalogError(DomainError): ...
```
```python
# domain/plate_formats.py — a implementar
def text_pattern(text: str) -> str: ...

class PlateFormatCatalog:
    def __init__(self, formats: Sequence[PlateFormat]) -> None: ...
    @property
    def formats(self) -> tuple[PlateFormat, ...]: ...
    def patterns_of_length(self, length: int) -> tuple[str, ...]: ...
    def matching(self, text: str) -> tuple[PlateFormat, ...]: ...
    def matching_with_pattern(self, text: str, pattern: str) -> tuple[PlateFormat, ...]: ...
```

## Comportamiento esperado
1. `text_pattern(text)`: si `text` no cumple `PLATE_TEXT_REGEX` → `InvalidPlateTextError("texto de placa inválido (longitud N)")`.
   Devuelve una cadena donde cada letra se convierte en `L` y cada dígito en `D`.
2. `PlateFormatCatalog.__init__`: si `formats` está vacío → `PlateFormatCatalogError("el catálogo de formatos está vacío")`;
   si hay `format_id` repetidos → `PlateFormatCatalogError("format_id repetido: <id>")`. Guarda `tuple(formats)` en el orden recibido.
3. `formats` devuelve la tupla guardada.
4. `patterns_of_length(length)`: patrones distintos cuyo `len(pattern) == length`, ordenados alfabéticamente (`sorted`). Tupla vacía si no hay.
5. `matching(text)`: formatos cuyo `matches(text)` es verdadero, en el orden del catálogo.
6. `matching_with_pattern(text, pattern)`: igual que `matching` pero además `fmt.pattern == pattern`.
7. El módulo no contiene datos de formatos: el catálogo real llega desde configuración (spec 006).
8. `tests/fixtures/plate_catalog.py` expone `build_test_catalog() -> PlateFormatCatalog` con **exactamente**
   estos formatos, en este orden (idénticos a docs/03-modelo-datos.md §4):

| format_id | pattern | regex | verified | vehicle_types |
|---|---|---|---|---|
| co_particular_publico | LLLDDD | `^[A-Z]{3}[0-9]{3}$` | True | car, bus, truck |
| co_diplomatico_2015 | LLLDDD | `^[MDCAO][A-Z]{2}[0-9]{3}$` | True | car, bus, truck |
| co_moto_diplomatica | LLLDDD | `^MCD[0-9]{3}$` | True | motorcycle |
| co_moto | LLLDDL | `^[A-Z]{3}[0-9]{2}[A-Z]$` | True | motorcycle |
| co_moto_antigua | LLLDD | `^[A-Z]{3}[0-9]{2}$` | True | motorcycle |
| co_motocarro | DDDLLL | `^[0-9]{3}[A-Z]{3}$` | True | car, motorcycle, bus, truck |
| co_diplomatico_antiguo | LLDDDD | `^(CD\|CC\|AT\|OI)[0-9]{4}$` | True | car, bus, truck |
| co_remolque | LDDDDD | `^[RS][0-9]{5}$` | False | car, motorcycle, bus, truck |
| co_importacion_temporal | LDDDD | `^T[0-9]{4}$` | False | car, motorcycle, bus, truck |

   `category` = el `format_id` y `source` = `"fixture sintético"` en el fixture.

## Casos borde y manejo de errores
- `matching("")` no lanza: devuelve `()` (ninguna regex del catálogo acepta vacío).
- `patterns_of_length(0)` devuelve `()`.

## Tests de aceptación
```python
# tests/fixtures/plate_catalog.py
from __future__ import annotations

from lector_placas.domain.entities import PlateFormat, VehicleType
from lector_placas.domain.plate_formats import PlateFormatCatalog

_ALL = frozenset(VehicleType)
_CARS = frozenset({VehicleType.CAR, VehicleType.BUS, VehicleType.TRUCK})
_MOTO = frozenset({VehicleType.MOTORCYCLE})

_ROWS: tuple[tuple[str, str, str, bool, frozenset[VehicleType]], ...] = (
    ("co_particular_publico", "LLLDDD", r"^[A-Z]{3}[0-9]{3}$", True, _CARS),
    ("co_diplomatico_2015", "LLLDDD", r"^[MDCAO][A-Z]{2}[0-9]{3}$", True, _CARS),
    ("co_moto_diplomatica", "LLLDDD", r"^MCD[0-9]{3}$", True, _MOTO),
    ("co_moto", "LLLDDL", r"^[A-Z]{3}[0-9]{2}[A-Z]$", True, _MOTO),
    ("co_moto_antigua", "LLLDD", r"^[A-Z]{3}[0-9]{2}$", True, _MOTO),
    ("co_motocarro", "DDDLLL", r"^[0-9]{3}[A-Z]{3}$", True, _ALL),
    ("co_diplomatico_antiguo", "LLDDDD", r"^(CD|CC|AT|OI)[0-9]{4}$", True, _CARS),
    ("co_remolque", "LDDDDD", r"^[RS][0-9]{5}$", False, _ALL),
    ("co_importacion_temporal", "LDDDD", r"^T[0-9]{4}$", False, _ALL),
)


def build_test_catalog() -> PlateFormatCatalog:
    return PlateFormatCatalog([
        PlateFormat(fid, fid, pattern, regex, verified, types, "fixture sintético")
        for fid, pattern, regex, verified, types in _ROWS
    ])
```
```python
# tests/unit/domain/test_plate_formats.py
from __future__ import annotations

import pytest

from lector_placas.domain.entities import PlateFormat, VehicleType
from lector_placas.domain.errors import InvalidPlateTextError, PlateFormatCatalogError
from lector_placas.domain.plate_formats import PlateFormatCatalog, text_pattern
from tests.fixtures.plate_catalog import build_test_catalog


@pytest.mark.parametrize("text,expected", [
    ("ABC123", "LLLDDD"), ("XYZ98K", "LLLDDL"), ("123ABC", "DDDLLL"), ("R12345", "LDDDDD"),
])
def test_text_pattern(text: str, expected: str) -> None:
    assert text_pattern(text) == expected


@pytest.mark.parametrize("text", ["", "abc123", "AB-123", "ABCDEFGHIJK"])
def test_text_pattern_rejects_invalid(text: str) -> None:
    with pytest.raises(InvalidPlateTextError):
        text_pattern(text)


def test_catalog_rejects_empty_and_duplicates() -> None:
    with pytest.raises(PlateFormatCatalogError):
        PlateFormatCatalog([])
    fmt = build_test_catalog().formats[0]
    with pytest.raises(PlateFormatCatalogError):
        PlateFormatCatalog([fmt, fmt])


def test_patterns_of_length_sorted_and_distinct() -> None:
    catalog = build_test_catalog()
    assert catalog.patterns_of_length(6) == ("DDDLLL", "LDDDDD", "LLDDDD", "LLLDDD", "LLLDDL")
    assert catalog.patterns_of_length(5) == ("LDDDD", "LLLDD")
    assert catalog.patterns_of_length(4) == ()


def test_matching_returns_catalog_order() -> None:
    ids = [f.format_id for f in build_test_catalog().matching("ABC123")]
    assert ids == ["co_particular_publico", "co_diplomatico_2015"]


def test_matching_moto_and_unverified() -> None:
    catalog = build_test_catalog()
    assert [f.format_id for f in catalog.matching("XYZ98K")] == ["co_moto"]
    assert [f.format_id for f in catalog.matching("R12345")] == ["co_remolque"]
    assert catalog.matching("") == ()


def test_matching_with_pattern_filters_pattern() -> None:
    catalog = build_test_catalog()
    assert catalog.matching_with_pattern("MCD123", "LLLDDD")[-1].format_id == "co_moto_diplomatica"
    assert catalog.matching_with_pattern("ABC123", "LLLDDL") == ()


def test_formats_property_keeps_input() -> None:
    fmt = PlateFormat("x_1", "c", "LD", "^[A-Z][0-9]$", True, frozenset({VehicleType.CAR}), "s")
    assert PlateFormatCatalog([fmt]).formats == (fmt,)
```

## Fuera de alcance
Corrección posicional (003), consolidación (004), carga desde YAML (006).

## Definition of Done
- [ ] `uv run pytest tests/unit/domain tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
