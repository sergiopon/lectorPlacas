# 041 - Búsqueda de avistamientos y listado de corridas (`SightingBrowser`)

## Objetivo
Dar a la GUI (specs 043–045) consultas de solo lectura: buscar avistamientos combinando estado, prefijo de placa,
corrida y rango de fechas, contarlos para paginar, y listar las corridas. Es un puerto nuevo (`SightingBrowser`),
separado de `PlateRepository` para no obligar a sus otras implementaciones a cambiar.

## Depende de
005, 020.

## Archivos rectores aplicables
- ARQUITECTURA.md §4 (puerto `SightingBrowser`), §6 (módulos ≤ 300 líneas, errores envueltos con `from e`).
- docs/02-contratos.md §4 (`RunStatus`, `RunRecord`, `SightingQuery`, `SightingBrowser` y su tabla de pre/postcondiciones).
- reglas-seguridad.md SEG-15 (SQL solo parametrizado), SEG-05/SEG-26 (sin placa en logs ni errores).
- docs/03-modelo-datos.md (esquema; **no cambia**: no hay migración).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py` (añadir `RunStatus`, `RunRecord`, `SightingQuery`, `SightingBrowser`)
- `src/lector_placas/adapters/persistence/rows.py` (nuevo: conversión de filas y fechas compartida)
- `src/lector_placas/adapters/persistence/sqlcipher_browser.py` (nuevo: `SqlCipherSightingBrowser`)
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py` (usa `rows.py`; añade `browser()`)
- `tests/fixtures/fakes.py` (añadir `search_sightings`, `count_sightings` y `list_runs` a `InMemoryPlateRepository`)
- `tests/unit/application/test_sighting_query.py` (nuevo)
- `tests/integration/test_sqlcipher_browser.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# application/ports.py
class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: int
    profile: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    frames_processed: int | None
    sightings_confirmed: int | None
    sightings_unverified: int | None
    tracks_without_reading: int | None
    processing_ms: int | None

@dataclass(frozen=True, slots=True)
class SightingQuery:
    status: ReviewStatus | None = None
    plate_prefix: str | None = None
    run_id: int | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    def __post_init__(self) -> None: ...

class SightingBrowser(Protocol):
    def search_sightings(self, query: SightingQuery, limit: int, offset: int) -> list[SightingRecord]: ...
    def count_sightings(self, query: SightingQuery) -> int: ...
    def list_runs(self, limit: int, offset: int) -> list[RunRecord]: ...

# adapters/persistence/rows.py
SIGHTING_COLUMNS: Final[str]            # lista de columnas del SELECT de avistamientos, en el orden de row_to_record
def to_db_time(value: datetime) -> str: ...
def from_db_time(value: str) -> datetime: ...
def row_to_record(row: tuple[Any, ...]) -> SightingRecord: ...

# adapters/persistence/sqlcipher_browser.py
class SqlCipherSightingBrowser:
    def __init__(self, connection: sqlcipher3.dbapi2.Connection) -> None: ...
    # implementa SightingBrowser

# adapters/persistence/sqlcipher_repository.py
class SqlCipherPlateRepository:
    def browser(self) -> SqlCipherSightingBrowser: ...
```

## Comportamiento esperado
1. `SightingQuery.__post_init__` (lanza `InvalidEntityError`):
   - `plate_prefix`, si no es `None`, debe cumplir `^[A-Z0-9]{1,10}$` (no se normaliza: la GUI ya envía mayúsculas).
     El mensaje de error **no** incluye el valor recibido (SEG-26): `"plate_prefix inválido"`.
   - `run_id`, si no es `None`, debe ser `>= 1`.
   - `created_from` y `created_to`, si no son `None`, deben tener `tzinfo`; si ambos existen, `created_to > created_from`.
2. `RunRecord` no valida (lo construye solo el adaptador desde filas válidas por el esquema).
3. `rows.py`: se **mueven** a este módulo `to_db_time`, `from_db_time`, la conversión de fila a `SightingRecord`
   (hoy `_row_to_record` y sus auxiliares `_split_reasons`, `_split_format_ids`) y la lista de columnas del SELECT de
   avistamientos. `sqlcipher_repository.py` los importa desde ahí y **sigue exponiendo** `to_db_time` y `from_db_time`
   con esos nombres (importándolos), para no romper a quien ya los importa. El comportamiento del repositorio no cambia.
4. `SqlCipherPlateRepository.browser()` devuelve un `SqlCipherSightingBrowser` que usa la misma conexión del
   repositorio (mismo hilo, misma vida útil). Tras `close()` del repositorio, cualquier consulta del navegador lanza
   `RepositoryError`.
5. `SqlCipherSightingBrowser.search_sightings(query, limit, offset)`:
   - `1 <= limit <= 10000` y `offset >= 0`; si no, `RepositoryError("parámetros de paginación inválidos")`.
   - Una única consulta SQL **constante** (sin construir SQL con f-strings ni concatenación, SEG-15), con cada filtro
     escrito como `(? IS NULL OR <condición>)`:
     estado `status = ?`; prefijo `substr(plate_text, 1, length(?)) = ?` (se compara con el texto **vigente**
     `plate_text`, no con `ocr_text`); corrida `run_id = ?`; desde `created_at >= ?`; hasta `created_at < ?`. Las fechas
     se pasan con `to_db_time` (ISO-8601 UTC con microsegundos, comparable como texto).
   - Orden `sighting_id DESC`, `LIMIT ? OFFSET ?`. Devuelve `SightingRecord` con `row_to_record`.
   - Errores de `sqlcipher3` → `RepositoryError("search_sightings falló") from e`.
6. `count_sightings(query)`: mismo `WHERE` que la búsqueda con `SELECT count(*)`; devuelve `int`. Errores →
   `RepositoryError("count_sightings falló") from e`.
7. `list_runs(limit, offset)`: misma validación de paginación; selecciona `run_id, profile, status, started_at,
   finished_at, duration_ms, frames_processed, sightings_confirmed, sightings_unverified, tracks_without_reading,
   processing_ms` de `runs`, orden `run_id DESC`. `status` → `RunStatus(valor)`; fechas con `from_db_time`
   (`finished_at` puede ser `NULL`). Errores → `RepositoryError("list_runs falló") from e`.
8. `sqlcipher_browser.py` ≤ 300 líneas; `sqlcipher_repository.py` no debe crecer (la extracción a `rows.py` lo reduce).
9. `InMemoryPlateRepository` (fake de tests) implementa también los tres métodos con la misma semántica (filtros, orden
   descendente, validación de paginación con `RepositoryError`). Para `list_runs` usa lo que ya guarda en `self.runs`
   (`StoredRun`); las corridas sin terminar tienen estado `RUNNING` y campos de estadísticas `None`. Añade también
   `browser()` que devuelve el propio fake, igual que el adaptador real devuelve su navegador.

## Casos borde y manejo de errores
- `SightingQuery()` sin filtros devuelve todo.
- El prefijo compara por inicio exacto: `"AB"` encuentra `ABC123` y no `XAB123`.
- Tras una corrección en revisión, la búsqueda por prefijo usa el texto corregido.
- Los mensajes de error no contienen texto de placa ni el prefijo buscado.

## Tests de aceptación
1. `tests/unit/application/test_sighting_query.py`:
   - `test_query_defaults_are_valid`: `SightingQuery()` se construye.
   - `test_query_rejects_invalid_prefix`: `"ab1"`, `""`, `"ABC-12"` y un texto de 11 caracteres lanzan
     `InvalidEntityError`; el mensaje no contiene el valor recibido.
   - `test_query_rejects_run_id_below_one`.
   - `test_query_rejects_naive_dates` y `test_query_rejects_inverted_range` (hasta igual o anterior a desde).
2. `tests/integration/test_sqlcipher_browser.py` (marcador `integration`, como `tests/integration/test_sqlcipher_repository.py`,
   con BD real en `tmp_path` y el `FakeKeyProvider` de `tests/fixtures/fakes.py`; placas sintéticas como `ABC123`,
   `ABD456`, `XYZ98K`). Siembra dos corridas (una terminada con estadísticas, otra sin terminar) y avistamientos con
   estados y `created_at` distintos. Casos:
   - `test_search_without_filters_returns_all_descending`.
   - `test_search_filters_by_status`, `test_search_filters_by_prefix` (incluye que `"AB"` no encuentra `XAB...`),
     `test_search_filters_by_run`, `test_search_filters_by_date_range` (desde inclusivo, hasta exclusivo),
     `test_search_combines_filters`.
   - `test_prefix_uses_corrected_text`: tras `record_review(..., CORRECTED, "XYZ98K", ...)` el prefijo `"XYZ"` lo
     encuentra y el prefijo del texto OCR original ya no.
   - `test_count_matches_search_without_pagination` para varias consultas.
   - `test_pagination_limit_offset` y `test_invalid_pagination_raises` (limit 0, limit 10001, offset -1).
   - `test_list_runs_descending_with_status_and_stats`: la corrida sin terminar es `RUNNING` con `finished_at` `None`.
   - `test_browser_after_close_raises_repository_error`.
3. Los tests existentes de `tests/integration/test_sqlcipher_repository.py` y `tests/review/` pasan sin cambios.

## Definition of Done
- `uv run pytest tests/unit tests/integration/test_sqlcipher_browser.py tests/integration/test_sqlcipher_repository.py tests/review` pasa.
- `uv run pytest tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- `grep -nE "execute\(f|execute\(.*%|execute\(.*\+" src/` vacío (SEG-15).
