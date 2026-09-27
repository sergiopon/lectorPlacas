# 034 - Adaptador: interfaz de revisión dentro de la ventana

## Objetivo
Reemplazar la interacción por terminal de `OpenCvReviewUI` (spec 027) por una interfaz completa dentro de la ventana
OpenCV: teclas leídas con un bucle de eventos continuo (la ventana nunca queda "sin responder"), campo de texto para
corregir y un diseño legible (tema oscuro, recorte grande, datos y ayuda de teclas).

## Depende de
027.

## Motivo (corrección 2026-09-26)
Con OpenCV 4.14 (backend Qt5 sobre XWayland en GNOME), `cv2.imshow` + un único `cv2.waitKey(1)` seguido de un `input()`
bloqueante deja la ventana sin procesar eventos: no se dibuja o GNOME la marca "no responde". Toda la interacción debe
ocurrir dentro de un bucle que llame `waitKey` periódicamente. Además, mostrar el texto de placa solo en la ventana (no en
la terminal) reduce su exposición.

## Archivos rectores aplicables
- ARQUITECTURA.md §4 (puerto `ReviewUI` sin cambios), §6 (funciones ≤ 20 sentencias, complejidad ≤ 8, docstrings).
- reglas-seguridad.md SEG-05 (sin placas en logs), SEG-07 (el recorte descifrado solo en memoria).

## Archivos a crear/modificar
- `src/lector_placas/adapters/review/opencv_review_ui.py` (reescritura completa)
- `tests/unit/adapters/test_opencv_review_ui.py` (reescritura completa con los tests de abajo)

## Dependencias externas
Ninguna nueva (opencv-python==4.14.0.94, numpy).

## Interfaces y tipos involucrados
```python
# de application/ports.py (sin cambios)
class ReviewAction(StrEnum): CONFIRM = "confirm"; CORRECT = "correct"; REJECT = "reject"; SKIP = "skip"; QUIT = "quit"
@dataclass(frozen=True, slots=True)
class ReviewDecision: action: ReviewAction; corrected_text: str | None = None
class ReviewUI(Protocol):
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...
# de domain/entities.py: SightingRecord, PLATE_TEXT_REGEX (^[A-Z0-9]{1,10}$)
```
```python
# adapters/review/opencv_review_ui.py — a implementar
WINDOW_NAME: Final[str] = "lector-placas: revision"
CANVAS_WIDTH: Final[int] = 960
CANVAS_HEIGHT: Final[int] = 600
MARGIN: Final[int] = 20
CROP_AREA_HEIGHT: Final[int] = 320
POLL_MS: Final[int] = 50
MAX_PLATE_CHARS: Final[int] = 10
KEY_ESC: Final[int] = 27
KEYS_ENTER: Final[frozenset[int]] = frozenset({10, 13})
KEYS_BACKSPACE: Final[frozenset[int]] = frozenset({8, 127})
BACKGROUND: Final[tuple[int, int, int]] = (32, 32, 32)
TEXT_COLOR: Final[tuple[int, int, int]] = (235, 235, 235)
MUTED_COLOR: Final[tuple[int, int, int]] = (160, 160, 160)
ACCENT_COLOR: Final[tuple[int, int, int]] = (80, 200, 255)
ERROR_COLOR: Final[tuple[int, int, int]] = (80, 80, 255)
MENU_TEXT: Final[str] = "[C] confirmar   [E] editar   [R] rechazar   [S] saltar   [Q] salir"
EDIT_HINT: Final[str] = "[Enter] guardar   [Esc] cancelar"
INVALID_KEY: Final[str] = "tecla no valida"
INVALID_TEXT: Final[str] = "texto invalido"
KEY_TO_ACTION: Final[Mapping[str, ReviewAction]] = MappingProxyType({
    "c": ReviewAction.CONFIRM, "r": ReviewAction.REJECT, "s": ReviewAction.SKIP, "q": ReviewAction.QUIT})

class WindowBackend(Protocol):
    def show(self, image: ImageBGR) -> None: ...
    def wait_key(self, delay_ms: int) -> int: ...     # -1 si no hubo tecla
    def is_open(self) -> bool: ...
    def close(self) -> None: ...

class OpenCvWindow:
    def __init__(self, name: str = WINDOW_NAME) -> None: ...
    def show(self, image: ImageBGR) -> None: ...
    def wait_key(self, delay_ms: int) -> int: ...
    def is_open(self) -> bool: ...
    def close(self) -> None: ...

@dataclass(frozen=True, slots=True, eq=False)
class ReviewView:
    record: SightingRecord
    crop: ImageBGR | None
    typed: str | None        # None = modo menú; str = modo edición (texto escrito hasta ahora)
    message: str | None

def render_review_frame(view: ReviewView) -> ImageBGR: ...

class OpenCvReviewUI:
    def __init__(self, window: WindowBackend | None = None, poll_ms: int = POLL_MS) -> None: ...
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...
```

## Comportamiento esperado
1. `OpenCvWindow`: `show` crea la ventana la primera vez con `cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)` y luego
   `cv2.imshow(name, image)`. `wait_key(ms)` devuelve `cv2.waitKey(ms)`. `is_open()`: `True` si aún no se creó; si no,
   `cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) >= 1`, y `cv2.error` → `False`. `close()`: si se creó,
   `cv2.destroyWindow(name)` y `cv2.waitKey(1)`, ignorando solo `cv2.error`.
2. `render_review_frame(view)` (función pura, **solo texto ASCII** porque las fuentes Hershey no dibujan tildes):
   - Lienzo `np.full((CANVAS_HEIGHT, CANVAS_WIDTH, 3), BACKGROUND, np.uint8)`.
   - Área del recorte: `x ∈ [MARGIN, CANVAS_WIDTH - MARGIN)`, `y ∈ [MARGIN, MARGIN + CROP_AREA_HEIGHT)`. Con recorte:
     escala `min(ancho_area / w, alto_area / h)`; `cv2.resize` con `INTER_CUBIC` si la escala es > 1, si no `INTER_AREA`;
     se pega centrado en el área. Sin recorte: texto `"sin recorte"` en `MUTED_COLOR` centrado en el área.
   - Debajo del área, con `cv2.FONT_HERSHEY_SIMPLEX` y `cv2.LINE_AA`, empezando en `y = MARGIN + CROP_AREA_HEIGHT + 45`
     y avanzando 45 px por línea:
     1. `f"#{sighting_id}  lectura: {plate_text}"` en `ACCENT_COLOR`, escala 1.0, grosor 2.
     2. `f"tipo: {vehicle_type}   confianza: {confidence:.2f}   acuerdo: {agreement:.2f}   lecturas: {num_readings}"` en
        `TEXT_COLOR`, escala 0.65, grosor 1.
     3. `f"razones: {', '.join(r.value for r in reasons) or '-'}"` en `MUTED_COLOR`, escala 0.6, grosor 1.
     4. Modo menú: `MENU_TEXT` en `TEXT_COLOR`; modo edición: `f"corregir: {typed}_   {EDIT_HINT}"` en `ACCENT_COLOR`;
        escala 0.7, grosor 2.
     5. Si `message`: `message` en `ERROR_COLOR`, escala 0.65, grosor 2.
3. `OpenCvReviewUI.ask(record, crop)`: estado inicial modo menú (`typed = None`, `message = None`). Bucle:
   - Si `not window.is_open()` → `ReviewDecision(ReviewAction.QUIT)`.
   - `window.show(render_review_frame(ReviewView(record, crop, typed, message)))`; `key = window.wait_key(poll_ms)`.
   - `key < 0` → siguiente vuelta (esto mantiene viva la ventana). Si no, `code = key & 0xFF`.
   - **Modo menú:** `code == KEY_ESC` → QUIT. `chr(code).lower() == "e"` → modo edición con `typed = ""`, `message = None`.
     Si `chr(code).lower()` está en `KEY_TO_ACTION` → `ReviewDecision(acción)`. Cualquier otra tecla → `message = INVALID_KEY`.
   - **Modo edición:** `KEY_ESC` → vuelve a modo menú (`typed = None`, `message = None`). Tecla en `KEYS_ENTER`: si `typed`
     cumple `PLATE_TEXT_REGEX` → `ReviewDecision(ReviewAction.CORRECT, typed)`; si no → `message = INVALID_TEXT`.
     `KEYS_BACKSPACE` → quita el último carácter. Otro código: `ch = chr(code).upper()`; si `ch` está en `A-Z` o `0-9` y
     `len(typed) < MAX_PLATE_CHARS` → se añade y `message = None`; si no, se ignora.
   - Divide en helpers privados (p. ej. `_handle_menu_key`, `_handle_edit_key`) para respetar ≤ 20 sentencias y
     complejidad ≤ 8.
   - **No escribe nada en la terminal** (ni `print` ni `sys.stdout`): el texto de placa solo se muestra en la ventana.
4. `close()` → `window.close()`.

## Casos borde y manejo de errores
- Cerrar la ventana con la X equivale a salir (QUIT); lo ya decidido queda guardado por el caso de uso.
- Ninguna excepción de OpenCV sale de `OpenCvWindow` salvo al crear la ventana (sin display → `cv2.error` se propaga
  como error inesperado de la CLI, código 1).

## Tests de aceptación
```python
# tests/unit/adapters/test_opencv_review_ui.py
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from lector_placas.adapters.review.opencv_review_ui import (
    BACKGROUND,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CROP_AREA_HEIGHT,
    MARGIN,
    OpenCvReviewUI,
    ReviewView,
    render_review_frame,
)
from lector_placas.application.ports import ReviewAction
from lector_placas.domain.entities import ReviewStatus, SightingRecord, UnverifiedReason, VehicleType

RECORD = SightingRecord(
    1, 1, 0, 0, 1, VehicleType.CAR, "ABC123", "ABC123", 0.5, 0.5, 2, ReviewStatus.UNVERIFIED,
    (UnverifiedReason.LOW_CONFIDENCE,), (), None, datetime(2026, 9, 26, tzinfo=UTC), None,
)


class FakeWindow:
    def __init__(self, keys: list[int], open_frames: int | None = None) -> None:
        self.keys = list(keys)
        self.frames: list[np.ndarray] = []
        self.open_frames = open_frames
        self.closed = False

    def show(self, image: np.ndarray) -> None:
        self.frames.append(image)

    def wait_key(self, delay_ms: int) -> int:
        if not self.keys:
            raise AssertionError("teclas agotadas")
        return self.keys.pop(0)

    def is_open(self) -> bool:
        return self.open_frames is None or len(self.frames) < self.open_frames

    def close(self) -> None:
        self.closed = True


def ask(keys: list[int], crop: np.ndarray | None = None):  # type: ignore[no-untyped-def]
    window = FakeWindow(keys)
    decision = OpenCvReviewUI(window=window).ask(RECORD, crop)
    return decision, window


def test_idle_polling_keeps_window_alive_then_confirms() -> None:
    decision, window = ask([-1, -1, ord("c")])
    assert decision.action is ReviewAction.CONFIRM
    assert len(window.frames) == 3
    assert window.frames[0].shape == (CANVAS_HEIGHT, CANVAS_WIDTH, 3)
    assert window.frames[0].dtype == np.uint8


@pytest.mark.parametrize("key,action", [
    (ord("R"), ReviewAction.REJECT), (ord("s"), ReviewAction.SKIP), (ord("q"), ReviewAction.QUIT), (27, ReviewAction.QUIT),
])
def test_menu_keys(key: int, action: ReviewAction) -> None:
    assert ask([key])[0].action is action


def test_invalid_menu_key_is_ignored() -> None:
    decision, window = ask([ord("x"), ord("c")])
    assert decision.action is ReviewAction.CONFIRM
    assert len(window.frames) == 2


def test_edit_types_uppercase_and_saves() -> None:
    keys = [ord("e"), ord("a"), ord("b"), ord("c"), ord("1"), ord("2"), ord("8"), 13]
    decision, _ = ask(keys)
    assert (decision.action, decision.corrected_text) == (ReviewAction.CORRECT, "ABC128")


def test_edit_backspace_ignores_symbols_and_limits_length() -> None:
    keys = [ord("e"), ord("a"), ord("b"), 8, ord("-"), ord("c"), 13]
    assert ask(keys)[0].corrected_text == "AC"
    long_keys = [ord("e"), *[ord("1")] * 12, 10]
    assert ask(long_keys)[0].corrected_text == "1" * 10


def test_empty_correction_is_rejected_then_fixed() -> None:
    keys = [ord("e"), 13, ord("x"), ord("y"), ord("z"), ord("9"), ord("9"), ord("9"), 13]
    assert ask(keys)[0].corrected_text == "XYZ999"


def test_escape_in_edit_returns_to_menu() -> None:
    assert ask([ord("e"), ord("a"), 27, ord("s")])[0].action is ReviewAction.SKIP


def test_closed_window_quits_without_drawing() -> None:
    window = FakeWindow([], open_frames=0)
    assert OpenCvReviewUI(window=window).ask(RECORD, None).action is ReviewAction.QUIT
    assert window.frames == []


def test_nothing_is_written_to_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    ask([ord("e"), ord("a"), 13])
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_close_delegates_to_window() -> None:
    window = FakeWindow([])
    OpenCvReviewUI(window=window).close()
    assert window.closed


def test_render_places_crop_in_center_of_area() -> None:
    crop = np.zeros((20, 60, 3), np.uint8)
    crop[:, :] = (0, 0, 255)
    frame = render_review_frame(ReviewView(RECORD, crop, None, None))
    center_y = MARGIN + CROP_AREA_HEIGHT // 2
    assert frame[center_y, CANVAS_WIDTH // 2].tolist() == [0, 0, 255]
    assert frame[2, 2].tolist() == list(BACKGROUND)


def test_render_without_crop_and_in_edit_mode() -> None:
    frame = render_review_frame(ReviewView(RECORD, None, "AB", "texto invalido"))
    assert frame.shape == (CANVAS_HEIGHT, CANVAS_WIDTH, 3)
    assert frame[2, 2].tolist() == list(BACKGROUND)
```

## Fuera de alcance
`ReviewSightings` (027) y la CLI no cambian: `commands.py` sigue creando `OpenCvReviewUI()`.

## Definition of Done
- [ ] `uv run pytest tests/unit tests/architecture tests/review` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `grep -n "print(\|sys.stdout\|input(" src/lector_placas/adapters/review/opencv_review_ui.py` vacío.
