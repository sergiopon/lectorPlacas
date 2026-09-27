# 040 - Aplicación: progreso y cancelación de `ProcessVideo`

## Objetivo
Permitir que quien ejecuta `ProcessVideo` (la GUI, spec 043) reciba el avance del procesamiento y pueda cancelarlo de
forma cooperativa, sin cambiar el comportamiento de la CLI.

## Depende de
024.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 (application depende solo de Protocols), §6 (tamaño de funciones, errores propios).
- docs/02-contratos.md §1 (`ProcessingCancelledError`), §4 (`ProgressUpdate`, `ProgressReporter`), §7 (cancelación).
- reglas-seguridad.md SEG-05 (sin placas en logs).

## Archivos a crear/modificar
- `src/lector_placas/domain/errors.py` (añadir `ProcessingCancelledError`)
- `src/lector_placas/application/ports.py` (añadir `ProgressUpdate` y `ProgressReporter`)
- `src/lector_placas/application/process_video.py` (parámetro `progress`)
- `tests/unit/application/test_process_video_progress.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# domain/errors.py
class ProcessingCancelledError(LectorPlacasError):
    """El operador canceló el procesamiento de un video."""

# application/ports.py
@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    frames_decoded: int
    frames_processed: int
    position_ms: int
    duration_ms: int | None
    sightings_saved: int
    def __post_init__(self) -> None: ...
    @property
    def fraction(self) -> float | None: ...

class ProgressReporter(Protocol):
    def report(self, update: ProgressUpdate) -> None: ...
    def cancel_requested(self) -> bool: ...

# application/process_video.py
class ProcessVideo:
    def execute(
        self, video_path: Path, video_sha256: str, progress: ProgressReporter | None = None
    ) -> RunResult: ...
```

## Comportamiento esperado
1. `ProgressUpdate.__post_init__`: `frames_decoded`, `frames_processed`, `position_ms` y `sightings_saved` deben ser
   `>= 0`, y `duration_ms` `None` o `>= 0`; si no, `InvalidEntityError` con el nombre del campo en el mensaje.
2. `ProgressUpdate.fraction`: `None` si `duration_ms` es `None` o `0`; si no, `min(1.0, position_ms / duration_ms)`.
3. `ProgressReporter`: docstrings con Precondiciones/Postcondiciones/Raises como los demás puertos: `report` se llama
   desde el hilo que ejecuta el caso de uso y no lanza; `cancel_requested` puede llamarse desde cualquier hilo.
4. `ProcessVideo.execute(video_path, video_sha256, progress=None)`:
   - Con `progress=None` el comportamiento es idéntico al actual (mismas llamadas a los puertos, mismo número de llamadas
     a `clock.now()`, mismos logs). Los tests existentes de la spec 024 deben pasar sin cambios.
   - Con `progress`: por **cada frame decodificado**, antes de consultar el muestreador, si
     `progress.cancel_requested()` es `True` se lanza `ProcessingCancelledError("procesamiento cancelado por el operador")`.
   - Tras procesar cada frame **muestreado** (después de finalizar los tracks inactivos de ese frame), se llama una vez a
     `progress.report(ProgressUpdate(...))` con los contadores acumulados: `frames_decoded`, `frames_processed`,
     `position_ms = frame.timestamp_ms`, `duration_ms = info.duration_ms` y
     `sightings_saved = sightings_confirmed + sightings_unverified`. Los frames descartados por el muestreador no generan
     reporte.
   - La cancelación recorre el camino de error existente: `_fail_run` cierra la corrida con `succeeded=False` y
     estadísticas parciales, registra `corrida fallida run_id=<id> error=ProcessingCancelledError` y se relanza la
     excepción. Los tracks aún abiertos **no** se finalizan ni se guardan; los avistamientos ya guardados se conservan.
   - Si `progress.report` o `progress.cancel_requested` lanzan un `LectorPlacasError`, se trata como cualquier otro error
     del pipeline (camino de `_fail_run`).
5. Las funciones siguen dentro de los límites de ARQUITECTURA §6 (≤ 20 sentencias, ≤ 6 argumentos, complejidad ≤ 8).
   Se permite pasar `progress` y la duración del video a `_process_all_frames` o extraer un método auxiliar privado.
6. `ProgressUpdate` y `ProgressReporter` se exportan desde `application/ports.py` junto a los demás puertos. La CLI no
   cambia.

## Casos borde y manejo de errores
- Video sin duración conocida (`duration_ms=None`): se reporta igual; `fraction` es `None`.
- Cancelación pedida antes del primer frame: se lanza en el primer frame decodificado; la corrida existe (ya se llamó
  `start_run`) y queda fallida con 0 frames procesados.
- Los mensajes y logs no contienen texto de placa.

## Tests de aceptación
Archivo `tests/unit/application/test_process_video_progress.py`. Usa los mismos fakes y el mismo tipo de fixture que los
tests existentes de `ProcessVideo` (spec 024, `tests/unit/application/` y `tests/fixtures/fakes.py`), con un video
sintético de fake de al menos 6 frames, un muestreador que procese uno de cada dos y al menos un track con lecturas.
Define en el propio test un reporter de prueba que guarde las actualizaciones recibidas y que responda a
`cancel_requested` según una condición configurable. Casos:

1. `test_progress_update_rejects_negative_values`: cada campo entero negativo (y `duration_ms` negativo) lanza
   `InvalidEntityError`.
2. `test_progress_update_fraction`: `duration_ms=None` → `None`; `duration_ms=0` → `None`; `position_ms=500,
   duration_ms=1000` → `0.5`; `position_ms=1500, duration_ms=1000` → `1.0`.
3. `test_execute_without_progress_behaves_as_before`: sin reporter, el `RunResult` y lo guardado en el repositorio fake
   coinciden con lo que se obtiene al ejecutar con un reporter que nunca cancela.
4. `test_reports_once_per_processed_frame`: el número de reportes es igual a `stats.frames_processed`; `frames_decoded`
   y `frames_processed` crecen de forma monótona; `position_ms` del último reporte es el timestamp del último frame
   muestreado; `duration_ms` es la del `VideoInfo` del fake.
5. `test_sightings_saved_counts_persisted_tracks`: en el último reporte, `sightings_saved` es igual a los avistamientos
   guardados hasta ese momento (los que se finalizan solo al terminar el video no cuentan en ese reporte).
6. `test_cancel_raises_and_marks_run_failed`: el reporter cancela después del segundo reporte; `execute` lanza
   `ProcessingCancelledError`; el repositorio fake registra `finish_run` con `succeeded=False`; no se guardan
   avistamientos de tracks que seguían abiertos; se decodificaron menos frames que los del video.
7. `test_cancel_before_first_frame`: el reporter cancela desde el inicio; `execute` lanza `ProcessingCancelledError`,
   la corrida se inició y se cerró como fallida, y no hubo ningún reporte.

## Definition of Done
- `uv run pytest tests/unit/application` pasa (incluidos los tests existentes de `ProcessVideo`).
- `uv run pytest tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
