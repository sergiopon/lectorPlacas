# 052 - Revisión: decisión "placa borrosa" (estado `illegible`, esquema v2)

## Objetivo
El operador pidió (2026-09-27) una opción de revisión "placa borrosa". Hoy solo puede confirmar, corregir o rechazar,
y "rechazar" mezcla dos cosas distintas:
- **no es una placa** (detección falsa, fragmento): la decisión actual `REJECTED`;
- **es una placa, pero ni un humano la puede leer** en el recorte: la decisión nueva `ILLEGIBLE`.

Separarlas da un dato que hoy no existe: qué fracción de las placas reales se pierde por calidad de imagen. Es la
evidencia para la Fase 2 de docs/07 (hallazgo 4, "la mayoría de las placas están borrosas"). Además, las borrosas no
deben entrar en el CER ni en el reentrenamiento: no tienen texto verdadero.

Esta spec cubre dominio, aplicación, persistencia (con la primera migración de esquema, v1 → v2), métricas de revisión,
CLI y la ventana OpenCV. La GUI (botón, atajo y filtro) es la spec 053. Aquí solo se añaden las entradas de los mapas de
etiquetas y colores de la GUI, para que no falle al encontrar el estado nuevo.

## Depende de
020, 027, 034, 038, 046.

## Archivos rectores aplicables
- docs/02-contratos.md (`ReviewStatus`, `ReviewAction`, `ReviewSummary`, `ReviewMetrics`, `record_review`; ya actualizados).
- docs/03-modelo-datos.md §1 (esquema v2 y migración; ya actualizado).
- ARQUITECTURA.md: límites de §6; los módulos de persistencia no importan capas superiores.
- reglas-seguridad.md SEG-01 (BD cifrada), SEG-05/SEG-26 (sin texto de placa en logs, auditoría ni errores).

## Archivos a crear/modificar
- `src/lector_placas/domain/entities.py`
- `src/lector_placas/application/ports.py`
- `src/lector_placas/application/review_sightings.py`
- `src/lector_placas/adapters/persistence/schema.sql`
- `src/lector_placas/adapters/persistence/migrations.py` (nuevo)
- `src/lector_placas/adapters/persistence/sqlcipher_repository.py`
- `src/lector_placas/adapters/review/opencv_review_ui.py`
- `src/lector_placas/evaluation/review_metrics.py`
- `src/lector_placas/cli/commands.py`
- `src/lector_placas/cli/main.py`
- `src/lector_placas/gui/labels.py`
- `src/lector_placas/gui/theme.py`
- `tests/integration/test_sqlcipher_repository.py`
- `tests/integration/test_schema_migration.py` (nuevo)
- `tests/unit/application/test_decide_sighting.py`
- `tests/unit/application/test_review_sightings.py`
- `tests/unit/evaluation/test_review_metrics.py`
- `tests/unit/adapters/test_opencv_review_ui.py`

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
- `ReviewStatus.ILLEGIBLE = "illegible"`, **al final** del enum.
- `ReviewAction.ILLEGIBLE = "illegible"`, **al final** del enum (después de `QUIT`).
- `ReviewSummary` gana `illegible: int = 0` como **último** campo (con valor por defecto, para que las construcciones
  posicionales existentes sigan valiendo).
- `ReviewMetrics` gana `confirmed_illegible: int` y `unverified_illegible: int`, **al final** de la dataclass.
- `SCHEMA_VERSION = 2`. Nuevo módulo `adapters/persistence/migrations.py` con una función pública
  `migrate_v1_to_v2(connection) -> None` (el tipo de la conexión es el de `sqlcipher3`, como en el repositorio).
- `PlateRepository.record_review` mantiene la firma. `status` admite ahora `ILLEGIBLE`, que se trata igual que
  `REJECTED`.

## Comportamiento esperado

### Dominio y aplicación
1. `ILLEGIBLE` es un estado final de revisión, igual que `REJECTED`: no se vincula a ninguna placa (`plate_id = NULL`),
   `plate_text` y `ocr_text` no cambian y no admite `corrected_text`.
2. `review_sightings.APPLICABLE_ACTIONS` añade `ILLEGIBLE → ReviewStatus.ILLEGIBLE`, así que lo usan tanto
   `ReviewSightings` (cola) como `DecideSighting` (un avistamiento suelto).
3. Contadores y resumen: `ReviewSightings` cuenta `illegible` en su `ReviewSummary`.
4. Detalle de auditoría: `confirmados=<n> corregidos=<n> rechazados=<n> borrosas=<n> omitidos=<n>`. El campo
   `borrosas` va entre `rechazados` y `omitidos`, tanto en la cola como en `DecideSighting`. Nunca lleva texto de placa.

### Persistencia
5. `schema.sql`: el `CHECK` de `sightings.status` admite `'illegible'`. Ningún otro cambio en el script.
6. `SqlCipherPlateRepository`:
   - `_REVIEWABLE_STATUSES` incluye `ILLEGIBLE`, y `record_review(..., ILLEGIBLE, None, t)` hace el mismo `UPDATE` que
     `REJECTED` (`status`, `plate_id = NULL`, `reviewed_at`). `ILLEGIBLE` con `corrected_text` →
     `RepositoryError("corrected_text solo se admite con CORRECTED")`, como hoy.
   - Versión al abrir: vacía → inserta 2; 1 → `migrate_v1_to_v2` y sigue; 2 → sigue; cualquier otra →
     `RepositoryError("versión de esquema no soportada")` (como hoy).
7. `migrate_v1_to_v2(connection)`:
   1. `PRAGMA foreign_keys = OFF` (fuera de transacción).
   2. `BEGIN IMMEDIATE`, explícito. No sirve `executescript`, porque hace commit implícito.
   3. Crea `sightings_v2` con **la misma definición** que `sightings` en `schema.sql` (columnas, tipos, `CHECK`,
      `REFERENCES`, `UNIQUE`, `AUTOINCREMENT`), salvo el `CHECK` de `status` ya ampliado.
   4. `INSERT INTO sightings_v2 (<todas las columnas, en orden>) SELECT <las mismas> FROM sightings`, conservando
      `sighting_id`.
   5. `DROP TABLE sightings`; `ALTER TABLE sightings_v2 RENAME TO sightings`.
   6. Recrea los cuatro índices de `sightings` de `schema.sql` (`idx_sightings_status`, `idx_sightings_created_at`,
      `idx_sightings_plate_id`, `idx_sightings_crop_ref` con su `WHERE`), con las mismas sentencias.
   7. `UPDATE schema_version SET version = 2`; `COMMIT`.
   8. `PRAGMA foreign_key_check`: si devuelve filas → `RepositoryError("migración de esquema fallida")`.
      Luego `PRAGMA foreign_keys = ON`.
   9. Cualquier `sqlcipher.Error` entre 2 y 7 → `ROLLBACK` y `RepositoryError("migración de esquema fallida")`
      encadenada. Si falla, la BD queda en v1 intacta (el DDL de SQLite es transaccional). El repositorio cierra la
      conexión antes de propagar el error.
   10. Log `INFO` `"esquema migrado de v1 a v2 avistamientos=<n>"` (solo el conteo, sin placas).

### Métricas, CLI y ventana OpenCV
8. `compute_review_metrics`: `confirmed_illegible` = auditadas de origen confirmado que quedaron `ILLEGIBLE`;
   `unverified_illegible` = de origen sin verificar que quedaron `ILLEGIBLE`. `precision_confirmed` sigue siendo
   `confirmed_kept / confirmed_audited`: una confirmada automática que resultó ilegible **no** cuenta como acierto.
   Los pares del CER siguen siendo solo `CONFIRMED`/`CORRECTED` revisados (las ilegibles no tienen verdad).
9. CLI:
   - `lector review` imprime `confirmados=… corregidos=… rechazados=… borrosas=… omitidos=…`.
   - `EXPORT_STATUS_CHOICES` añade `"illegible"` al final.
   - La línea de `evaluate-review` no cambia (los campos nuevos solo van al reporte JSON, que ya se genera con `asdict`).
   - `export-reviewed` no cambia: solo exporta `CONFIRMED` y `CORRECTED`.
10. `opencv_review_ui.py`: la tecla `b` (y `B`, con el mismo tratamiento de mayúsculas que las demás) → `ILLEGIBLE`.
    `MENU_TEXT = "[C] confirmar   [E] editar   [R] rechazar   [B] borrosa   [S] saltar   [Q] salir"`.
11. GUI, solo los mapas (el resto es la spec 053):
    - `STATUS_LABELS[ILLEGIBLE] = "borrosa"` y `STATUS_BADGES[ILLEGIBLE] = "Borrosa"`.
    - `STATUS_COLORS[ILLEGIBLE] = ("#374151", "#F3F4F6")` (gris; texto sobre fondo con contraste AA, como los demás).

## Casos borde y manejo de errores
- Una BD v1 con avistamientos de todos los estados migra sin perder filas, con los mismos `sighting_id`, textos,
  estados, razones, `crop_ref` y `reviewed_at`.
- Abrir dos veces una BD ya migrada no vuelve a migrar.
- Después de migrar, el siguiente `sighting_id` que asigna SQLite es mayor que todos los existentes
  (`AUTOINCREMENT` sobrevive al renombrado). Lo comprueba un test; si fallara, la migración debe copiar la fila de
  `sqlite_sequence` y el implementador reporta la desviación.
- Mensajes de error y logs sin texto de placa.

**Nota para el operador:** antes de abrir por primera vez la BD real con esta versión, copiar `data/lector.db` (cifrada)
a un lugar seguro. La migración es atómica, pero es la primera del proyecto.

## Tests de aceptación

### `tests/integration/test_schema_migration.py` (nuevo)
Con una BD SQLCipher real en `tmp_path` y el `KeyProvider` de prueba que ya usan los tests de integración del
repositorio. La BD v1 se construye así: se abre con el repositorio (queda en v2), se guardan avistamientos, y luego, con
la conexión cruda, se recrea `sightings` con el `CHECK` de v1 (copiando las filas) y se pone `schema_version` a 1. Se
cierra y se vuelve a abrir con el repositorio.

1. `test_v1_database_is_migrated_preserving_rows`: una BD v1 con avistamientos `unverified`, `confirmed`, `corrected` y
   `rejected` (uno revisado con texto corregido) se abre. `schema_version` pasa a 2 y `list_sightings(None, …)`
   devuelve los mismos registros, campo a campo, que antes de migrar.
2. `test_migrated_database_accepts_illegible`: tras migrar, `record_review(id, ILLEGIBLE, None, t)` funciona y el
   registro queda `ILLEGIBLE`, con `plate_text` y `ocr_text` intactos.
3. `test_migration_keeps_indexes_and_autoincrement`: tras migrar existen los cuatro índices de `sightings`, y un
   avistamiento nuevo recibe un `sighting_id` mayor que el máximo previo.
4. `test_reopening_migrated_database_does_not_migrate_again`: se abre dos veces; la segunda no registra el log de
   migración y los datos no cambian.
5. `test_failed_migration_leaves_v1_intact`: se fuerza un fallo dentro de la transacción (p. ej. una tabla
   `sightings_v2` preexistente que hace fallar el `CREATE`); abrir lanza `RepositoryError` y, con la conexión cruda,
   `schema_version` sigue en 1 y las filas siguen ahí.

### `tests/integration/test_sqlcipher_repository.py`
6. `test_unsupported_schema_version`: pasa a usar una versión no soportada distinta de 1 y 2 (p. ej. 99), con el mismo
   resultado esperado.
7. `test_illegible_review_unlinks_plate`: un avistamiento `confirmed` vinculado a una placa pasa a `ILLEGIBLE`: queda
   sin `plate_id` y sin cambios de texto. `ILLEGIBLE` con `corrected_text` lanza `RepositoryError`.

### `tests/unit/application/test_decide_sighting.py`
8. Los detalles esperados del caso parametrizado de auditoría incluyen `borrosas=0`, y se añade la fila
   `ILLEGIBLE` → `"confirmados=0 corregidos=0 rechazados=0 borrosas=1 omitidos=0"`.
9. `test_illegible_marks_illegible`: `DecideSighting` con `ILLEGIBLE` deja el estado `ILLEGIBLE` y `reviewed_at` con la
   hora del reloj.

### `tests/unit/application/test_review_sightings.py`
10. `test_queue_counts_illegible`: una cola con una decisión `ILLEGIBLE` devuelve `ReviewSummary` con `illegible == 1`
    y el avistamiento queda `ILLEGIBLE`.

### `tests/unit/evaluation/test_review_metrics.py`
11. `test_illegible_counts_and_precision`: una confirmada automática auditada como `ILLEGIBLE` suma a
    `confirmed_illegible`, cuenta en `confirmed_audited` y no en `confirmed_kept`. Una sin verificar marcada `ILLEGIBLE`
    suma a `unverified_illegible`. Ninguna entra en los pares del CER.

### `tests/unit/adapters/test_opencv_review_ui.py`
12. `test_b_key_marks_illegible`: pulsar `b` en modo menú devuelve `ReviewDecision(ILLEGIBLE)`, y `MENU_TEXT` contiene
    `[B] borrosa`.

Los demás tests existentes pasan sin cambios. `tests/unit/gui/test_labels.py` sigue exigiendo un texto por estado.

## Fuera de alcance
- Botón, atajo y filtro en la GUI (spec 053).
- Detectar borrosidad de forma automática.
- Usar las borrosas para ajustar umbrales (Fase 2 de docs/07).

## Definition of Done
- `uv run pytest tests/integration tests/unit tests/review tests/architecture` pasa (GUI con `QT_QPA_PLATFORM=offscreen`).
- `uv run pytest` completo pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- Solo cambian los archivos listados.
