# 027 - Aplicación y adaptador: revisión humana de lecturas dudosas

## Objetivo
Implementar el caso de uso `ReviewSightings` (recorre los avistamientos `unverified`) y el adaptador
`OpenCvReviewUI` (muestra el recorte ampliado y pide la decisión por terminal).

## Depende de
005.

## Archivos rectores aplicables
- Requisito RF-27. reglas-seguridad.md SEG-05 (auditoría sin placas), SEG-07 (recorte solo en memoria).
- docs/02-contratos.md §4 (`ReviewDecision`, `ReviewAction`, `ReviewUI`) y §5.

## Archivos a crear/modificar
- `src/lector_placas/application/review_sightings.py`
- `src/lector_placas/adapters/review/opencv_review_ui.py`
- `tests/unit/application/test_review_sightings.py`
- `tests/unit/adapters/test_opencv_review_ui.py`

## Dependencias externas
opencv-python==4.14.0.94 (ventana; requiere entorno gráfico solo cuando `show=True`).

## Interfaces y tipos involucrados
```python
# de application/ports.py
class ReviewAction(StrEnum): CONFIRM = "confirm"; CORRECT = "correct"; REJECT = "reject"; SKIP = "skip"; QUIT = "quit"
@dataclass(frozen=True, slots=True)
class ReviewDecision: action: ReviewAction; corrected_text: str | None = None
class ReviewUI(Protocol):
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...
class PlateRepository(Protocol):
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
    def record_review(self, sighting_id: int, status: ReviewStatus, corrected_text: str | None, reviewed_at: datetime) -> None: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
class CropStore(Protocol):
    def load(self, crop_ref: str) -> ImageBGR: ...
class Clock(Protocol):
    def now(self) -> datetime: ...
# de domain: SightingRecord, ReviewStatus, PLATE_TEXT_REGEX; errors: CropNotFoundError, ReviewError
```
```python
# application/review_sightings.py — a implementar
@dataclass(frozen=True, slots=True)
class ReviewSummary:
    confirmed: int
    corrected: int
    rejected: int
    skipped: int

class ReviewSightings:
    def __init__(self, repository: PlateRepository, crop_store: CropStore, ui: ReviewUI, clock: Clock) -> None: ...
    def execute(self, limit: int) -> ReviewSummary: ...

# adapters/review/opencv_review_ui.py — a implementar
WINDOW_NAME: Final[str] = "lector-placas: revision"
SCALE: Final[int] = 3
PROMPT: Final[str] = "[c]onfirmar  [e]ditar  [r]echazar  [s]altar  [q]salir: "
KEY_TO_ACTION: Final[Mapping[str, ReviewAction]] = MappingProxyType({
    "c": ReviewAction.CONFIRM, "e": ReviewAction.CORRECT, "r": ReviewAction.REJECT,
    "s": ReviewAction.SKIP, "q": ReviewAction.QUIT})

class OpenCvReviewUI:
    def __init__(self, read_line: Callable[[str], str] = input,
                 write: Callable[[str], object] = sys.stdout.write, show: bool = True) -> None: ...
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...
```

## Comportamiento esperado
1. `ReviewSightings.execute(limit)`: `limit` fuera de 1..10000 → `ReviewError`. `records = repository.list_sightings(ReviewStatus.UNVERIFIED, limit, 0)`.
   En `try/finally` (el `finally` llama `ui.close()`), por cada registro:
   - `crop`: `None` si `crop_ref is None`; si no `crop_store.load(crop_ref)`, y `CropNotFoundError` → `None`.
   - `decision = ui.ask(record, crop)`; `reviewed_at = clock.now()`.
   - CONFIRM → `record_review(id, CONFIRMED, None, reviewed_at)`; CORRECT → `record_review(id, CORRECTED, decision.corrected_text, reviewed_at)`;
     REJECT → `record_review(id, REJECTED, None, reviewed_at)`; SKIP → cuenta omitido; QUIT → termina el bucle.
   Al final: `repository.log_event(AuditEvent.REVIEW, clock.now(), f"confirmados={..} corregidos={..} rechazados={..} omitidos={..}")`
   y devuelve `ReviewSummary`.
2. `OpenCvReviewUI.ask(record, crop)`:
   - Si `show` y hay `crop`: `cv2.imshow(WINDOW_NAME, cv2.resize(crop, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST))` y `cv2.waitKey(1)`.
   - Escribe con `write` una línea: `f"#{id} lectura={plate_text} confianza={confidence:.2f} acuerdo={agreement:.2f} lecturas={num_readings} tipo={vehicle_type} razones={','.join(reasons)}\n"`
     (esto es interfaz con el operador, no log; está permitido mostrar el texto).
   - Bucle: `answer = read_line(PROMPT).strip().lower()`; si no está en `KEY_TO_ACTION` → `write("opción inválida\n")` y repetir.
   - Para `e`: bucle `text = read_line("texto corregido: ").strip().upper()`; vacío → vuelve al menú principal;
     si cumple `PLATE_TEXT_REGEX` → `ReviewDecision(CORRECT, text)`; si no → `write("texto inválido\n")` y repetir.
   - Otras teclas → `ReviewDecision(acción)`.
   - `EOFError` de `read_line` → `ReviewDecision(ReviewAction.QUIT)`.
3. `close()`: si `show`, `cv2.destroyWindow(WINDOW_NAME)` ignorando solo `cv2.error`.

## Casos borde y manejo de errores
- El texto de la placa no se registra en logs ni en auditoría.

## Tests de aceptación
```python
# tests/unit/application/test_review_sightings.py
from __future__ import annotations

import numpy as np
import pytest

from lector_placas.application.ports import AuditEvent, ReviewAction, ReviewDecision, RunStart, VideoInfo
from lector_placas.application.review_sightings import ReviewSightings
from lector_placas.domain.entities import (
    ConsolidatedPlate, ReviewStatus, Sighting, SightingRecord, UnverifiedReason, VehicleType,
)
from lector_placas.domain.errors import ReviewError
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository

UNVERIFIED = ConsolidatedPlate("ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED,
                               (UnverifiedReason.LOW_CONFIDENCE,), ())


class ScriptedUI:
    def __init__(self, decisions: list[ReviewDecision]) -> None:
        self.decisions = decisions
        self.crops: list[object] = []
        self.closed = False

    def ask(self, record: SightingRecord, crop: np.ndarray | None) -> ReviewDecision:
        self.crops.append(None if crop is None else crop.shape)
        return self.decisions.pop(0)

    def close(self) -> None:
        self.closed = True


def seed(count: int) -> tuple[InMemoryPlateRepository, InMemoryCropStore]:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))
    for track in range(count):
        ref = crops.save(np.zeros((3, 9, 3), np.uint8)) if track == 0 else "f" * 32
        repo.save_sighting(Sighting(run_id, track, 0, 1, VehicleType.CAR, UNVERIFIED, ref, START))
    return repo, crops


def test_applies_decisions_and_stops_on_quit() -> None:
    repo, crops = seed(5)
    ui = ScriptedUI([ReviewDecision(ReviewAction.CONFIRM), ReviewDecision(ReviewAction.CORRECT, "ABC128"),
                     ReviewDecision(ReviewAction.REJECT), ReviewDecision(ReviewAction.SKIP),
                     ReviewDecision(ReviewAction.QUIT)])
    summary = ReviewSightings(repo, crops, ui, FakeClock()).execute(10)
    assert (summary.confirmed, summary.corrected, summary.rejected, summary.skipped) == (1, 1, 1, 1)
    statuses = [r.status for r in repo.list_sightings(None, 10, 0)]
    assert statuses == [ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED, ReviewStatus.REJECTED,
                        ReviewStatus.UNVERIFIED, ReviewStatus.UNVERIFIED]
    assert repo.get_sighting(2).plate_text == "ABC128"
    assert ui.crops[:2] == [(3, 9, 3), None]
    assert ui.closed
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.REVIEW and "ABC" not in detail


def test_invalid_limit() -> None:
    repo, crops = seed(0)
    with pytest.raises(ReviewError):
        ReviewSightings(repo, crops, ScriptedUI([]), FakeClock()).execute(0)
```
```python
# tests/unit/adapters/test_opencv_review_ui.py
from __future__ import annotations

from datetime import UTC, datetime

from lector_placas.adapters.review.opencv_review_ui import OpenCvReviewUI
from lector_placas.application.ports import ReviewAction
from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType

RECORD = SightingRecord(1, 1, 0, 0, 1, VehicleType.CAR, "ABC123", "ABC123", 0.5, 0.5, 2,
                        ReviewStatus.UNVERIFIED, (), (), None, datetime(2026, 9, 24, tzinfo=UTC), None)


def ui(answers: list[str]) -> tuple[OpenCvReviewUI, list[str]]:
    output: list[str] = []
    queue = list(answers)

    def read_line(prompt: str) -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    return OpenCvReviewUI(read_line=read_line, write=output.append, show=False), output


def test_confirm_and_invalid_option() -> None:
    review, output = ui(["x", "C"])
    assert review.ask(RECORD, None).action is ReviewAction.CONFIRM
    assert "opción inválida\n" in output
    assert output[0].startswith("#1 lectura=ABC123")


def test_correct_with_validation() -> None:
    review, output = ui(["e", "abc-1", "abc128"])
    decision = review.ask(RECORD, None)
    assert (decision.action, decision.corrected_text) == (ReviewAction.CORRECT, "ABC128")
    assert "texto inválido\n" in output


def test_empty_correction_returns_to_menu() -> None:
    review, _ = ui(["e", "", "r"])
    assert review.ask(RECORD, None).action is ReviewAction.REJECT


def test_eof_quits() -> None:
    review, _ = ui([])
    assert review.ask(RECORD, None).action is ReviewAction.QUIT
    review.close()
```

## Fuera de alcance
Comando de CLI (spec 028).

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
