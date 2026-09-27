# 038 - Auditoría de confirmadas y métricas desde la revisión (`review --status`, `evaluate-review`)

## Objetivo
Medir la calidad real del sistema con los videos del usuario sin anotar ground truth: el operador audita una muestra de
avistamientos `confirmed` con la misma ventana de revisión, y `lector evaluate-review` calcula, a partir de las
decisiones guardadas, la precisión de las confirmadas, el desglose de las `unverified` y el CER sobre datos reales.

## Depende de
027, 029, 034.

## Archivos rectores aplicables
- reglas-seguridad.md: SEG-05/SEG-26 (sin placas en logs, reportes ni consola), SEG-20 (sin red), SEG-01 (BD cifrada).
- ARQUITECTURA.md: regla de dependencia (`evaluation` no importa `datasets` ni `cli`); la CLI compone.
- docs/04-evaluacion.md §3 y §4.

## Datos que ya existen (no se cambia el esquema)
- `SightingRecord.ocr_text`: texto que produjo el sistema (no cambia al revisar).
- `SightingRecord.plate_text`: texto vigente; `record_review(CORRECTED, texto)` lo sobrescribe.
- `SightingRecord.reasons`: vacío si y solo si el consolidador lo confirmó (`consolidation.py`: `CONFIRMED if not reasons`).
- `SightingRecord.reviewed_at`: no es `None` si un humano lo revisó.
- `record_review(id, CONFIRMED, None, t)` sobre un avistamiento ya `confirmed` es válido: conserva el texto y fija `reviewed_at`.

## Archivos a crear/modificar
- `src/lector_placas/application/review_sightings.py` (parámetro `status`)
- `src/lector_placas/cli/main.py` (`review --status`; registrar `evaluate-review`)
- `src/lector_placas/cli/commands.py` (`cmd_review` pasa el estado)
- `src/lector_placas/evaluation/review_metrics.py` (nuevo)
- `src/lector_placas/cli/review_evaluation_commands.py` (nuevo)
- `tests/unit/application/test_review_sightings_status.py` (nuevo)
- `tests/unit/evaluation/test_review_metrics.py` (nuevo)
- `tests/unit/cli/test_review_evaluation_cli.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
```python
# existentes
class PlateRepository(Protocol):
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
def character_error_rate(pairs: Sequence[tuple[str, str]]) -> float: ...   # (predicción, verdad); EvaluationError si vacío
def exact_match_rate(pairs: Sequence[tuple[str, str]]) -> float: ...
def write_report(reports_dir: Path, payload: Mapping[str, object], created_at: datetime) -> Path: ...
def _run_with_repository(config, keys, action) -> int: ...                  # cli/commands.py
# cli/evaluation_commands.py: PAGE_SIZE = 500, _reports_dir(config), _format_metric(value)
```
```python
# application/review_sightings.py — cambios
REVIEWABLE_STATUSES: Final[frozenset[ReviewStatus]] = frozenset({ReviewStatus.UNVERIFIED, ReviewStatus.CONFIRMED})
AUDIT_PAGE_SIZE: Final[int] = 500
class ReviewSightings:
    def execute(self, limit: int, status: ReviewStatus = ReviewStatus.UNVERIFIED) -> ReviewSummary: ...

# evaluation/review_metrics.py — nuevo
@dataclass(frozen=True, slots=True)
class ReviewMetrics:
    confirmed_total: int          # reasons == ()
    confirmed_audited: int        # reasons == () y reviewed_at no None
    confirmed_kept: int           # auditadas que siguen CONFIRMED
    confirmed_corrected: int      # auditadas ahora CORRECTED
    confirmed_rejected: int       # auditadas ahora REJECTED
    precision_confirmed: float | None   # confirmed_kept / confirmed_audited; None si no hay auditadas
    unverified_total: int         # reasons != ()
    unverified_confirmed: int
    unverified_corrected: int
    unverified_rejected: int
    unverified_pending: int       # status UNVERIFIED
    reason_counts: dict[str, int] # UnverifiedReason.value -> número de avistamientos con esa razón; claves ordenadas
    reviewed_readings: int        # pares usados para el CER
    cer: float | None             # None si reviewed_readings == 0
    exact_match_rate: float | None

def compute_review_metrics(records: Sequence[SightingRecord]) -> ReviewMetrics: ...

# cli/review_evaluation_commands.py — nuevo
def register_review_evaluation(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...
def cmd_evaluate_review(args: argparse.Namespace, config: AppConfig) -> int: ...
```

## Comportamiento esperado
1. `ReviewSightings.execute(limit, status)`:
   - `status` fuera de `REVIEWABLE_STATUSES` → `ReviewError(f"estado no revisable: {status.value}")`; `limit` se valida igual que hoy.
   - `UNVERIFIED`: comportamiento actual sin cambios.
   - `CONFIRMED`: recorre `list_sightings(CONFIRMED, AUDIT_PAGE_SIZE, offset)` página a página (offset += tamaño de página)
     y se queda con los que tienen `reviewed_at is None`, hasta reunir `limit` o agotar las páginas; luego los revisa con el
     mismo flujo (`_review`, `_apply`, cierre de la UI y `AuditEvent.REVIEW`). Una decisión `CONFIRM` sobre uno de ellos
     llama `record_review(id, CONFIRMED, None, t)` (ya lo hace `_apply`).
2. CLI `lector review [--limit N] [--status {unverified,confirmed}]` (por defecto `unverified`); `cmd_review` llama
   `use_case.execute(args.limit, ReviewStatus(args.status))`. El resumen en consola no cambia.
3. `compute_review_metrics(records)`:
   - Origen confirmado = `not record.reasons`; origen sin verificar = `bool(record.reasons)`.
   - Conteos según los campos del tipo. `reason_counts` cuenta cada razón una vez por avistamiento de origen sin verificar
     (revisado o no), con claves `UnverifiedReason.value` en orden alfabético.
   - Pares para el CER: `(record.ocr_text, record.plate_text)` de los avistamientos con `reviewed_at is not None` y
     `status in {CONFIRMED, CORRECTED}` (los rechazados no tienen verdad). `cer = character_error_rate(pares)` y
     `exact_match_rate(pares)` solo si hay pares; si no, ambos `None`.
   - Lista vacía → `EvaluationError("no hay avistamientos para evaluar")`.
4. CLI `lector evaluate-review` → `set_defaults(handler=cmd_evaluate_review, network=False, key="load")`; se registra con
   `register_review_evaluation(subparsers)` desde `main.build_parser` (después de `register_evaluation_commands`).
   - Con `_run_with_repository(config, commands.require_keys(args), action)`: lee todos los avistamientos con
     `list_sightings(None, PAGE_SIZE, offset)` página a página; `metrics = compute_review_metrics(records)`.
   - Payload: `{"kind": "review", **campos de ReviewMetrics}` (`dataclasses.asdict`), escrito con
     `write_report(_reports_dir(config), payload, clock.now())`.
   - stdout (una línea): `confirmed_audited=… precision_confirmed=… unverified_total=… unverified_pending=…
     reviewed_readings=… cer=… exact_match_rate=…` (métricas con `_format_metric`) y `reporte=<nombre>`. Devuelve 0.
   - Ningún texto de placa en consola ni en el reporte.

## Casos borde y manejo de errores
- La precisión de confirmadas es una estimación por muestreo: el reporte incluye `confirmed_audited` y `confirmed_total`
  para que se vea el tamaño de la muestra.
- Los avistamientos purgados por retención (90 días) salen de la métrica; es aceptable.

## Tests de aceptación
```python
# tests/unit/application/test_review_sightings_status.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.ports import ReviewAction, ReviewDecision, RunStart, VideoInfo
from lector_placas.application.review_sightings import ReviewSightings
from lector_placas.domain.entities import (
    ConsolidatedPlate, ReviewStatus, Sighting, SightingRecord, UnverifiedReason, VehicleType,
)
from lector_placas.domain.errors import ReviewError
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

CONFIRMED = ConsolidatedPlate("ABC123", 0.9, 0.9, 5, ReviewStatus.CONFIRMED, (), ())
UNVERIFIED = ConsolidatedPlate(
    "XYZ987", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED, (UnverifiedReason.LOW_CONFIDENCE,), ()
)


class ScriptedUI:
    def __init__(self, decisions: list[ReviewDecision]) -> None:
        self.decisions = decisions
        self.seen: list[int] = []

    def ask(self, record: SightingRecord, crop: np.ndarray | None) -> ReviewDecision:
        self.seen.append(record.sighting_id)
        return self.decisions.pop(0)

    def close(self) -> None:
        pass


def seed() -> InMemoryPlateRepository:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track, plate in enumerate((CONFIRMED, UNVERIFIED, CONFIRMED, CONFIRMED)):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, None, START))
    return repo


def test_audits_only_unreviewed_confirmed() -> None:
    repo = seed()
    repo.record_review(1, ReviewStatus.CONFIRMED, None, START)
    ui = ScriptedUI([ReviewDecision(ReviewAction.CORRECT, "ABC128"), ReviewDecision(ReviewAction.CONFIRM)])
    summary = ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(5, ReviewStatus.CONFIRMED)
    assert ui.seen == [3, 4]
    assert (summary.confirmed, summary.corrected) == (1, 1)
    assert repo.get_sighting(3).status is ReviewStatus.CORRECTED
    assert repo.get_sighting(4).reviewed_at is not None


def test_default_status_is_unverified_and_rejects_others() -> None:
    repo = seed()
    ui = ScriptedUI([ReviewDecision(ReviewAction.SKIP)])
    ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(5)
    assert ui.seen == [2]
    with pytest.raises(ReviewError):
        ReviewSightings(repo, InMemoryCropStore(), ui, FakeClock()).execute(5, ReviewStatus.REJECTED)
```
```python
# tests/unit/evaluation/test_review_metrics.py
from __future__ import annotations

import pytest

from lector_placas.application.ports import RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate, ReviewStatus, Sighting, UnverifiedReason, VehicleType,
)
from lector_placas.domain.errors import EvaluationError
from lector_placas.evaluation.review_metrics import compute_review_metrics
from tests.fixtures.fakes import START, InMemoryPlateRepository

CONFIRMED = ConsolidatedPlate("ABC123", 0.9, 0.9, 5, ReviewStatus.CONFIRMED, (), ())
UNVERIFIED = ConsolidatedPlate(
    "XYZ987", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED,
    (UnverifiedReason.LOW_CONFIDENCE, UnverifiedReason.LOW_AGREEMENT), (),
)


def test_metrics_from_review_decisions() -> None:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track, plate in enumerate((CONFIRMED,) * 3 + (UNVERIFIED,) * 3):
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, None, START))
    repo.record_review(1, ReviewStatus.CONFIRMED, None, START)
    repo.record_review(2, ReviewStatus.CORRECTED, "ABC128", START)
    repo.record_review(4, ReviewStatus.CONFIRMED, None, START)
    repo.record_review(5, ReviewStatus.REJECTED, None, START)
    metrics = compute_review_metrics(repo.list_sightings(None, 100, 0))
    assert (metrics.confirmed_total, metrics.confirmed_audited) == (3, 2)
    assert (metrics.confirmed_kept, metrics.confirmed_corrected, metrics.confirmed_rejected) == (1, 1, 0)
    assert metrics.precision_confirmed == pytest.approx(0.5)
    assert (metrics.unverified_total, metrics.unverified_confirmed, metrics.unverified_corrected) == (3, 1, 0)
    assert (metrics.unverified_rejected, metrics.unverified_pending) == (1, 1)
    assert metrics.reason_counts == {"low_agreement": 3, "low_confidence": 3}
    assert metrics.reviewed_readings == 3
    assert metrics.cer == pytest.approx(1 / 18)
    assert metrics.exact_match_rate == pytest.approx(2 / 3)


def test_no_reviews_gives_none_and_empty_raises() -> None:
    repo = InMemoryPlateRepository()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    repo.save_sighting(Sighting(run_id, 0, 0, 1, VehicleType.CAR, CONFIRMED, None, START))
    metrics = compute_review_metrics(repo.list_sightings(None, 100, 0))
    assert (metrics.precision_confirmed, metrics.cer, metrics.exact_match_rate) == (None, None, None)
    with pytest.raises(EvaluationError):
        compute_review_metrics([])
```
```python
# tests/unit/cli/test_review_evaluation_cli.py
from __future__ import annotations

from lector_placas.cli.main import build_parser
from lector_placas.cli.review_evaluation_commands import cmd_evaluate_review


def test_parser_review_status_and_evaluate_review() -> None:
    parser = build_parser()
    assert parser.parse_args(["review"]).status == "unverified"
    assert parser.parse_args(["review", "--status", "confirmed"]).status == "confirmed"
    args = parser.parse_args(["evaluate-review"])
    assert (args.handler, args.network, args.key) == (cmd_evaluate_review, False, "load")
```

## Fuera de alcance
Muestreo aleatorio de confirmadas (se auditan en orden de `sighting_id`). Cambios de esquema.

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde, incluidos los tests existentes de `ReviewSightings` y de la CLI.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `evaluation/review_metrics.py` no importa `lector_placas.datasets`, `infrastructure`, `adapters` ni `cli`.
