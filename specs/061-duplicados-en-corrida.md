# 061 - Duplicados de la misma placa en una corrida (`duplicate_of`)

## Objetivo
Al terminar una corrida con éxito, agrupar los avistamientos de esa corrida que leen exactamente la misma placa y
están cerca en el tiempo, conservar uno por grupo y marcar los demás con `duplicate_of` (columna creada por la spec
059). Los duplicados no se borran ni cambian de estado: salen de la vista por defecto del navegador de avistamientos
(GUI) y de la revisión por CLI.

## Depende de
041, 059, 060.

## Archivos rectores aplicables
- docs/09-enfoque-versatil.md §3.4 (D6) y §1.5; ADR-017 (decisión 4).
- reglas-seguridad.md SEG-05 (el log nuevo no lleva texto de placa), SEG-15.

## Archivos a crear/modificar
- `src/lector_placas/application/duplicates.py` (nuevo)
- `src/lector_placas/application/ports.py` (`PlateRepository.mark_duplicates`; `SightingQuery.include_duplicates`)
- `src/lector_placas/application/process_video.py`
- `src/lector_placas/application/review_sightings.py`
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py`
- `src/lector_placas/adapters/persistence/sqlcipher_browser.py`
- `src/lector_placas/infrastructure/config.py`
- `src/lector_placas/cli/composition.py`
- `config/lector.yaml`
- `tests/fixtures/fakes.py`
- `tests/unit/application/test_duplicates.py` (nuevo)
- `tests/unit/application/test_process_video_duplicates.py` (nuevo)
- `tests/unit/application/test_review_skips_duplicates.py` (nuevo)
- `tests/integration/test_mark_duplicates.py` (nuevo)
- `tests/unit/infrastructure/test_config.py` (un test nuevo)
- `tests/unit/cli/test_processing_settings.py` (un cambio de expectativa)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `application/duplicates.py` (nuevo; stdlib y `domain`)
- `@dataclass(frozen=True, slots=True) class DuplicateCandidate` con `sighting_id: int`, `plate_text: str`,
  `status: ReviewStatus`, `confidence: float`, `first_seen_ms: int`, `last_seen_ms: int`.
- `def find_duplicates(candidates: Sequence[DuplicateCandidate], window_ms: int) -> list[tuple[int, int]]`: devuelve
  pares `(sighting_id del duplicado, sighting_id del conservado)` ordenados por el primer elemento.

### `application/ports.py`
- `PlateRepository` gana `mark_duplicates(self, pairs: Sequence[tuple[int, int]]) -> None`.
- `SightingQuery` gana, **al final**, `include_duplicates: bool = False`.

### `application/process_video.py`
- `ProcessingSettings` gana, **al final** (después de `early_stop`), `dedup_window_ms: int = 0`. `__post_init__`
  añade: si no `0 <= dedup_window_ms <= 600_000` →
  `InvalidEntityError(f"dedup_window_ms debe estar en [0, 600000]: {dedup_window_ms}")`.
- `_Counters` gana `saved: list[DuplicateCandidate] = field(default_factory=list)` (importar `field` de
  `dataclasses`).

### `infrastructure/config.py` y `cli/composition.py`
- `ProfileConfig` gana, **al final** (después de `early_stop`), `dedup_window_ms: int` sin valor por defecto, con
  validador de campo: si no `0 <= value <= 600_000` →
  `ValueError(f"dedup_window_ms debe estar en [0, 600000]: {value}")`.
- `build_processing_settings` pasa además `dedup_window_ms=profile.dedup_window_ms`.

## Comportamiento esperado

### 1. `find_duplicates(candidates, window_ms)`
1. Agrupa los candidatos por `plate_text` exacto.
2. Dentro de cada texto, ordena por `(first_seen_ms, sighting_id)` y forma grupos así: el primero abre un grupo con
   `fin = last_seen_ms`; cada siguiente entra en el grupo abierto si `first_seen_ms - fin <= window_ms` (un solape da una
   diferencia negativa y entra) y entonces `fin = max(fin, last_seen_ms)`; si no, cierra el grupo y abre otro con él.
3. En cada grupo de 2 o más, el **conservado** es el mínimo según la clave
   `(0 si status is ReviewStatus.CONFIRMED else 1, -confidence, sighting_id)`. Cada uno de los demás produce el par
   `(su sighting_id, sighting_id del conservado)`.
4. Devuelve todos los pares ordenados por su primer elemento. Grupos de 1 no producen pares.

### 2. `ProcessVideo`
1. En `_save_track`, después de `sighting_id = deps.repository.save_sighting(sighting)`, se añade a `counters.saved`
   `DuplicateCandidate(sighting_id, plate.text, plate.status, plate.confidence, track.first_seen_ms, track.last_seen_ms)`.
   (`save_sighting` ya devuelve el id; hoy se descarta.)
2. En `_run`, dentro del `try`, justo después de `self._finalize(registry.pop_all(), run_id, counters)`:
   - si `settings.dedup_window_ms == 0`, no se hace nada más (ni log);
   - si no, `pairs = find_duplicates(counters.saved, settings.dedup_window_ms)`;
     `deps.repository.mark_duplicates(pairs)`; `logger.info("duplicados run_id=%d marcados=%d", run_id, len(pairs))`.
3. Una corrida cancelada o fallida no llega a ese paso y no marca duplicados.

### 3. Repositorio SQLCipher
`mark_duplicates(pairs)`: si `pairs` está vacío, no hace nada. Si no, en **una** transacción ejecuta, por cada par,
`UPDATE sightings SET duplicate_of = ? WHERE sighting_id = ?` con `(conservado, duplicado)`. `sqlcipher.Error` →
`RepositoryError("mark_duplicates falló")` y no queda ningún cambio (la transacción se deshace).
El fake `InMemoryPlateRepository.mark_duplicates` sustituye cada registro duplicado por
`dataclasses.replace(registro, duplicate_of=conservado)`.

### 4. Navegador de avistamientos
`_SEARCH_SQL` y `_COUNT_SQL` añaden, después del filtro de `created_at <`, la condición
`AND (? = 1 OR duplicate_of IS NULL)`; `_filter_params` añade al final el parámetro
`1 if query.include_duplicates else 0`. El fake: `_matches` añade
`and (query.include_duplicates or record.duplicate_of is None)`.

### 5. Revisión por CLI
`ReviewSightings._select`, en la rama `UNVERIFIED`, devuelve
`[r for r in self._repository.list_sightings(status, limit, 0) if r.duplicate_of is None]` (el límite se aplica antes de
filtrar). La rama de auditoría de confirmados filtra igual: en `_unreviewed_confirmed`, el criterio de selección pasa a
`record.reviewed_at is None and record.duplicate_of is None`.

### 6. Configuración
`config/lector.yaml`: en los cuatro perfiles se añade `dedup_window_ms: 30000` como **última** clave (después de
`early_stop`). Nada más cambia.

## Casos borde y manejo de errores
- `window_ms = 0` en `find_duplicates` (si se llamara) agrupa solo los que se solapan o se tocan; `ProcessVideo` no la
  llama con 0.
- Textos que difieren en un carácter no se agrupan nunca.
- Exportaciones CSV, `export-reviewed`, `export-legibility` y métricas no cambian: incluyen los duplicados.
- Ningún log, mensaje ni auditoría lleva texto de placa.

## Tests de aceptación (en prosa)
Fixtures sintéticos con placas inventadas.

**Test existente que cambia de expectativa (solo este):**
- `tests/unit/cli/test_processing_settings.py::test_build_processing_settings_copies_profile`: además comprueba
  `dedup_window_ms == 30000`.

`tests/unit/application/test_duplicates.py` (`C(id, texto, estado, confianza, inicio, fin)` abrevia `DuplicateCandidate`):
- `test_confirmed_wins_and_window_splits`: `C(1, "ABC123", UNVERIFIED, 0.8, 0, 1000)`,
  `C(2, "ABC123", CONFIRMED, 0.7, 5000, 6000)`, `C(3, "ABC123", UNVERIFIED, 0.9, 40000, 41000)`, ventana 30000 →
  `[(1, 2)]`.
- `test_overlap_groups_and_higher_confidence_wins`: `C(4, "XYZ98K", UNVERIFIED, 0.6, 0, 3000)`,
  `C(5, "XYZ98K", UNVERIFIED, 0.9, 1000, 2000)`, ventana 30000 → `[(4, 5)]`.
- `test_tie_keeps_lowest_id`: `C(6, "DEF456", UNVERIFIED, 0.5, 0, 100)`, `C(7, "DEF456", UNVERIFIED, 0.5, 200, 300)`,
  ventana 30000 → `[(7, 6)]`.
- `test_group_end_is_max_of_members`: `C(8, "GHI789", UNVERIFIED, 0.5, 0, 10000)`,
  `C(9, "GHI789", UNVERIFIED, 0.6, 2000, 3000)`, `C(10, "GHI789", UNVERIFIED, 0.7, 35000, 36000)`, ventana 30000 →
  `[(8, 10), (9, 10)]`.
- `test_different_texts_never_group`: `C(11, "ABC123", …, 0, 100)` y `C(12, "ABC124", …, 0, 100)` → `[]`.
- `test_empty_and_single`: `[]` → `[]`; un solo candidato → `[]`.

`tests/unit/application/test_process_video_duplicates.py`: reutiliza por importación desde
`tests.unit.application.test_process_video` `FakeSource`, `FakeSourceFactory`, `ScriptedVehicleDetector`,
`TwoTrackTracker`, `FixedPlateDetector`, `CyclingReader`, `ConstantQuality` y `SHA`, con un `build` propio que acepta
`dedup_window_ms` (consolidador con `ConsolidationPolicy(3, 0.9, 0.6, 0.1)`).
- `test_same_plate_two_tracks_marks_duplicate` (con `caplog` a INFO): `TwoTrackTracker`, lector
  `CyclingReader(["ABC123"])`, 10 frames, `dedup_window_ms=30000`: hay 2 avistamientos; el de `sighting_id` 2 tiene
  `duplicate_of == 1` y el 1 tiene `duplicate_of is None`; existe la línea de log
  `duplicados run_id=1 marcados=1`.
- `test_dedup_disabled`: igual con `dedup_window_ms=0`: ninguno tiene `duplicate_of` y no hay línea `duplicados`.
- `test_invalid_dedup_window`: `ProcessingSettings(..., dedup_window_ms=600001)` y `dedup_window_ms=-1` lanzan
  `InvalidEntityError`.

`tests/unit/application/test_review_skips_duplicates.py` (con `InMemoryPlateRepository`, `InMemoryCropStore`,
`FakeClock` y una UI falsa que registra los `sighting_id` que se le preguntan y siempre responde `SKIP`):
- `test_review_skips_duplicates`: dos avistamientos `UNVERIFIED`; `mark_duplicates([(2, 1)])`; `ReviewSightings(...)
  .execute(10)` pregunta solo por el 1.
- `test_browser_hides_duplicates_by_default`: con los mismos datos, `search_sightings(SightingQuery(), 10, 0)` devuelve
  solo el 1 y `count_sightings(SightingQuery())` es 1; con `SightingQuery(include_duplicates=True)` devuelve los dos y
  cuenta 2.

`tests/integration/test_mark_duplicates.py` (repositorio y navegador SQLCipher reales en `tmp_path`):
- `test_mark_and_read_back`: tres avistamientos; `mark_duplicates([(2, 1), (3, 1)])`; `get_sighting(2).duplicate_of
  == 1`, `get_sighting(3).duplicate_of == 1`, `get_sighting(1).duplicate_of is None`; `mark_duplicates([])` no lanza.
- `test_browser_filter`: con esos datos, `search_sightings(SightingQuery(), 10, 0)` devuelve solo el 1 y
  `count_sightings` es 1; con `include_duplicates=True`, 3 y 3.
- `test_invalid_target_rolls_back`: `mark_duplicates([(2, 1), (3, 999)])` lanza `RepositoryError` y el 2 sigue con
  `duplicate_of is None`.

`tests/unit/infrastructure/test_config.py` (añadir):
- `test_real_config_dedup_window`: los cuatro perfiles tienen `dedup_window_ms == 30000`; con `calle_lenta` a 600001 el
  mensaje contiene `dedup_window_ms debe estar en [0, 600000]: 600001`; con -1, contiene
  `dedup_window_ms debe estar en [0, 600000]: -1`.

## Fuera de alcance
- Agrupar textos parecidos (distancia de edición): PENDIENTE DE VALIDAR con el experimento E6 de docs/09.
- Propagar la decisión de revisión del conservado a sus duplicados.
- Mostrar el número de duplicados en la GUI (la web lo hará con `duplicates`).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde; solo cambia el test listado.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -nE "execute\(f|execute\(.*%|execute\(.*\+" src/` sin resultados (SEG-15).
