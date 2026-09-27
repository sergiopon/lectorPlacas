# 045 - GUI: pestaña "Exportar y retención" (CSV, purga manual y métricas de la revisión)

## Objetivo
Completar RF-36: exportar avistamientos a CSV, purgar por retención a mano y ver las métricas de la revisión (spec 038)
desde la GUI, con los mismos casos de uso que la CLI.

## Depende de
026, 025, 038, 042, 043, 044.

## Archivos rectores aplicables
- ADR-015; reglas-seguridad.md SEG-03 (purga), SEG-08 (CSV solo en `data/exports/`, auditado), SEG-26, SEG-27.
- docs/04-evaluacion.md §4 (métricas de la revisión: estimaciones por muestreo).

## Archivos a crear/modificar
- `src/lector_placas/gui/maintenance_tab.py` (nuevo)
- `src/lector_placas/gui/main_window.py` (inserta la pestaña y conecta `busy_changed`)
- `tests/unit/gui/test_maintenance_tab.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# existentes que se reutilizan
class ExportSightings:                       # application/export_sightings.py
    def __init__(self, repository: PlateRepository, export_store: ExportStore, clock: Clock) -> None: ...
    def execute(self, status: ReviewStatus | None) -> Path: ...
def build_purge(config, repository, crop_store, export_store, clock) -> PurgeExpiredData: ...   # cli/composition.py
def compute_review_metrics(records: Sequence[SightingRecord]) -> ReviewMetrics: ...           # evaluation/review_metrics.py

# gui/maintenance_tab.py
METRICS_PAGE_SIZE: Final[int] = 500
class MaintenanceTab(QWidget):
    def __init__(self, session: GuiSession) -> None: ...
    def export(self) -> None: ...
    def purge(self) -> None: ...
    def compute_metrics(self) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
```

## Comportamiento esperado
1. **Exportar**: `QComboBox` de estado ("Todos" + `STATUS_LABELS` de la spec 044) y botón "Exportar CSV".
   `export()`: `ExportSightings(session.repository, session.export_store, session.clock).execute(estado_o_None)`; muestra
   en una etiqueta `f"exportado: {path.name}"` (solo el nombre, como `cmd_export`). `ExportError` o `RepositoryError`
   → `QMessageBox.warning` con el mensaje. No abre el archivo ni el explorador.
2. **Retención**: etiqueta con la política vigente
   `f"Retención: recortes {crops_days} días · registros {records_days} días · entrenamiento {training_days} días"`
   tomada de `session.config.retention`. Botón "Purgar ahora": pide confirmación con `QMessageBox.question`
   ("Se borrarán los datos vencidos según la retención. ¿Continuar?"); con "Sí",
   `composition.build_purge(config, repository, crop_store, export_store, clock).execute()` y muestra
   `f"recortes={…} avistamientos={…} corridas={…} placas={…} exportaciones={…}"` (mismos campos que `cmd_purge`).
   Errores `LectorPlacasError` → `QMessageBox.warning`.
3. **Métricas de la revisión**: botón "Calcular". `compute_metrics()` lee todos los avistamientos con
   `session.repository.list_sightings(None, METRICS_PAGE_SIZE, offset)` página a página (hasta una página incompleta) y
   llama `compute_review_metrics(records)`. Muestra en un `QFormLayout`, con `percent` de la spec 044 para las tasas
   (o "n/d" si son `None`): confirmadas totales y auditadas, precisión de confirmadas, mantenidas/corregidas/rechazadas
   entre las auditadas, sin verificar totales y pendientes, sin verificar confirmadas/corregidas/rechazadas, lecturas
   revisadas, CER y tasa de coincidencia exacta, y el conteo por razón (una fila por clave de `reason_counts`).
   Debajo, la nota fija: "Estimación por muestreo sobre lo revisado; no sustituye la evaluación con ground truth
   (docs/04-evaluacion.md)". `EvaluationError` (sin avistamientos) → etiqueta "no hay avistamientos para evaluar".
   **No** escribe reporte a disco (la CLI `evaluate-review` sigue siendo la que genera el JSON).
4. `set_busy(True)` deshabilita "Exportar CSV" y "Purgar ahora" (escriben o borran mientras el hilo procesa);
   "Calcular" sigue habilitado (solo lee).
5. **`MainWindow`**: reemplaza la pestaña "Exportar y retención" por `MaintenanceTab(session)` y conecta
   `busy_changed` a `MaintenanceTab.set_busy`. Tras una purga manual, la pestaña "Avistamientos" se refresca
   (`SightingsTab.search`): `MaintenanceTab` expone una señal `data_changed = Signal()` que `MainWindow` conecta.
6. Ningún texto de placa en esta pestaña (las métricas son agregadas).

## Casos borde y manejo de errores
- Exportar sin avistamientos: `ExportSightings` escribe un CSV solo con cabecera (comportamiento actual de la spec 026).
- Purgar sin nada vencido: muestra todos los contadores en 0.

## Tests de aceptación
Sin pantalla (conftest de la spec 042), con `InMemoryPlateRepository`, `InMemoryCropStore` e `InMemoryExportStore` de
`tests/fixtures/fakes.py`; `QMessageBox` sustituido con `monkeypatch`; `composition.build_purge` sustituido cuando haga
falta.

1. `test_export_writes_and_shows_file_name`: con estado "Todos" y con `confirmed`; la etiqueta muestra solo el nombre.
2. `test_export_error_warns`: el almacén lanza `ExportError` → advertencia con el mensaje.
3. `test_retention_label_uses_config`.
4. `test_purge_asks_confirmation_and_reports_counts`; `test_purge_cancelled_does_nothing` (respuesta "No" → la purga no
   se ejecuta).
5. `test_purge_emits_data_changed`.
6. `test_metrics_paginates_and_displays`: con 1 200 avistamientos sintéticos (varias páginas) los valores mostrados
   coinciden con `compute_review_metrics` sobre la misma lista; tasas `None` se muestran "n/d".
7. `test_metrics_without_sightings_shows_message`.
8. `test_busy_disables_export_and_purge_only`.

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
