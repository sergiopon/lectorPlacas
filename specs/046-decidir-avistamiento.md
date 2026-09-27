# 046 - Aplicación: decidir sobre un avistamiento suelto (`DecideSighting`)

## Objetivo
La GUI rediseñada (specs 047–049) revisa las placas desde una galería: el operador elige una tarjeta y decide sobre
ella, sin una cola modal. Hace falta un caso de uso que aplique **una** decisión a **un** avistamiento con las mismas
reglas y la misma auditoría que `ReviewSightings` (spec 027).

## Depende de
027.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 (application depende solo de Protocols), §6 (límites de tamaño, errores propios).
- docs/02-contratos.md §4 (`PlateRepository.record_review`, `log_event`, `ReviewDecision`, `AuditEvent.REVIEW`).
- reglas-seguridad.md SEG-05 y SEG-26 (sin texto de placa en logs ni errores).

## Archivos a crear/modificar
- `src/lector_placas/application/review_sightings.py` (añadir `DecideSighting`)
- `tests/unit/application/test_decide_sighting.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# application/review_sightings.py
class DecideSighting:
    def __init__(self, repository: PlateRepository, clock: Clock) -> None: ...
    def execute(self, sighting_id: int, decision: ReviewDecision) -> SightingRecord: ...
```

## Comportamiento esperado
1. `execute(sighting_id, decision)`:
   - `CONFIRM` → `repository.record_review(sighting_id, CONFIRMED, None, clock.now())`.
   - `CORRECT` → `record_review(sighting_id, CORRECTED, decision.corrected_text, clock.now())`.
   - `REJECT` → `record_review(sighting_id, REJECTED, None, clock.now())`.
   - `SKIP` o `QUIT` → `ReviewError("acción no aplicable a un avistamiento: <valor>")` sin escribir nada.
   - Tras escribir registra `repository.log_event(AuditEvent.REVIEW, clock.now(), detalle)` con el mismo formato de
     detalle que `ReviewSightings` (`"confirmados=1 corregidos=0 rechazados=0 omitidos=0"`, con un 1 en la acción
     aplicada). El detalle nunca lleva texto de placa.
   - Devuelve `repository.get_sighting(sighting_id)` (el registro ya actualizado).
   - Los errores del repositorio (`SightingNotFoundError`, `RepositoryError`) se propagan sin envolver.
2. Se puede decidir sobre un avistamiento en cualquier estado (el operador puede cambiar de opinión: un rechazado se
   puede confirmar después). `ocr_text` nunca cambia (lo garantiza el repositorio).
3. `ReviewSightings` no cambia de comportamiento. Si se reutiliza el formateo del detalle, que sea con un auxiliar
   privado del módulo; los tests existentes de la spec 027 pasan sin cambios.

## Casos borde y manejo de errores
- `CORRECT` con texto inválido: `ReviewDecision` ya lo rechaza al construirse (spec 005); no se revalida.
- Ningún mensaje ni log contiene texto de placa.

## Tests de aceptación
Archivo `tests/unit/application/test_decide_sighting.py`, con `InMemoryPlateRepository` y `FakeClock` de
`tests/fixtures/fakes.py` y avistamientos sintéticos (`ABC123`, `XYZ98K`). Casos:

1. `test_confirm_marks_confirmed_and_returns_record`: estado `CONFIRMED`, `reviewed_at` = hora del reloj, el registro
   devuelto es el actualizado.
2. `test_correct_sets_plate_text_and_keeps_ocr_text`: `CORRECT` con `"XYZ98K"` → `plate_text == "XYZ98K"`,
   `ocr_text` sin cambios, estado `CORRECTED`.
3. `test_reject_marks_rejected`.
4. `test_skip_and_quit_raise_review_error_without_writing`: ambos lanzan `ReviewError`; el registro no cambió y no hay
   evento de auditoría nuevo.
5. `test_logs_review_audit_event_without_plate_text`: tras cada acción aplicada hay un evento `REVIEW` con el detalle
   esperado y el detalle no contiene el texto de la placa.
6. `test_can_change_decision_on_rejected`: rechazar y luego confirmar deja `CONFIRMED`.
7. `test_unknown_sighting_propagates_not_found`: id inexistente → `SightingNotFoundError`.

## Definition of Done
- `uv run pytest tests/unit/application tests/review` pasa.
- `uv run pytest tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
