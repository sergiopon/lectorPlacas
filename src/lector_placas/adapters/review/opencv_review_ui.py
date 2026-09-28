"""Interfaz de revisión completa dentro de una ventana OpenCV.

La ventana procesa eventos en un bucle continuo de `waitKey`, de modo que nunca queda "sin
responder"; tanto el menú como la edición del texto de placa ocurren dentro de ese bucle y nada se
escribe en la terminal, para reducir la exposición del texto leído.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

import cv2
import numpy as np

from lector_placas.application.ports import ImageBGR, ReviewAction, ReviewDecision
from lector_placas.domain.entities import PLATE_TEXT_REGEX, SightingRecord

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
MENU_TEXT: Final[str] = (
    "[C] confirmar   [E] editar   [R] rechazar   [B] borrosa   [S] saltar   [Q] salir"
)
EDIT_HINT: Final[str] = "[Enter] guardar   [Esc] cancelar"
INVALID_KEY: Final[str] = "tecla no valida"
INVALID_TEXT: Final[str] = "texto invalido"
KEY_TO_ACTION: Final[Mapping[str, ReviewAction]] = MappingProxyType(
    {
        "c": ReviewAction.CONFIRM,
        "r": ReviewAction.REJECT,
        "b": ReviewAction.ILLEGIBLE,
        "s": ReviewAction.SKIP,
        "q": ReviewAction.QUIT,
    }
)

_FONT: Final[int] = cv2.FONT_HERSHEY_SIMPLEX
_LINE_STEP: Final[int] = 45


class WindowBackend(Protocol):
    """Ventana mínima que necesita la interfaz de revisión."""

    def show(self, image: ImageBGR) -> None:
        """Dibuja una imagen en la ventana."""
        ...

    def wait_key(self, delay_ms: int) -> int:
        """Espera una tecla hasta `delay_ms` milisegundos; `-1` si no hubo."""
        ...

    def is_open(self) -> bool:
        """Indica si la ventana sigue abierta."""
        ...

    def close(self) -> None:
        """Cierra la ventana."""
        ...


class OpenCvWindow:
    """Ventana OpenCV real; crea la ventana de forma diferida y procesa eventos en `wait_key`."""

    def __init__(self, name: str = WINDOW_NAME) -> None:
        """Guarda el nombre de la ventana, que aún no se ha creado."""
        self._name = name
        self._created = False

    def show(self, image: ImageBGR) -> None:
        """Crea la ventana la primera vez y muestra la imagen."""
        if not self._created:
            cv2.namedWindow(self._name, cv2.WINDOW_AUTOSIZE)
            self._created = True
        cv2.imshow(self._name, image)

    def wait_key(self, delay_ms: int) -> int:
        """Espera hasta `delay_ms` milisegundos una tecla; `-1` si no hubo."""
        return cv2.waitKey(delay_ms)

    def is_open(self) -> bool:
        """Indica si la ventana sigue visible; `True` mientras no se haya creado."""
        if not self._created:
            return True
        try:
            return cv2.getWindowProperty(self._name, cv2.WND_PROP_VISIBLE) >= 1
        except cv2.error:
            return False

    def close(self) -> None:
        """Destruye la ventana si se había creado, ignorando errores de OpenCV."""
        if not self._created:
            return
        with contextlib.suppress(cv2.error):
            cv2.destroyWindow(self._name)
            cv2.waitKey(1)


@dataclass(frozen=True, slots=True, eq=False)
class ReviewView:
    """Estado que se dibuja en un fotograma de la revisión."""

    record: SightingRecord
    crop: ImageBGR | None
    typed: str | None
    message: str | None


def render_review_frame(view: ReviewView) -> ImageBGR:
    """Compone el lienzo que muestra el recorte y los datos del avistamiento.

    Args:
        view: estado actual de la revisión.

    Returns:
        Imagen BGR del tamaño del lienzo.
    """
    frame: ImageBGR = np.full((CANVAS_HEIGHT, CANVAS_WIDTH, 3), BACKGROUND, np.uint8)
    _draw_crop(frame, view.crop)
    _draw_details(frame, view)
    return frame


def _draw_crop(frame: ImageBGR, crop: ImageBGR | None) -> None:
    """Pega el recorte centrado en su área, o avisa que no hay recorte."""
    area_width = CANVAS_WIDTH - 2 * MARGIN
    area_height = CROP_AREA_HEIGHT
    if crop is None:
        _draw_centered_text(frame, "sin recorte", MUTED_COLOR, 0.7, 1)
        return
    scale = min(area_width / crop.shape[1], area_height / crop.shape[0])
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    resized = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=interpolation)
    height, width = resized.shape[:2]
    offset_x = MARGIN + (area_width - width) // 2
    offset_y = MARGIN + (area_height - height) // 2
    frame[offset_y : offset_y + height, offset_x : offset_x + width] = resized


def _draw_centered_text(
    frame: ImageBGR,
    text: str,
    color: tuple[int, int, int],
    scale: float,
    thickness: int,
) -> None:
    """Escribe un texto centrado en el área del recorte."""
    area_width = CANVAS_WIDTH - 2 * MARGIN
    area_height = CROP_AREA_HEIGHT
    (text_width, text_height), _ = cv2.getTextSize(text, _FONT, scale, thickness)
    origin = (MARGIN + (area_width - text_width) // 2, MARGIN + (area_height + text_height) // 2)
    _draw_text(frame, text, origin, color, scale, thickness)


def _draw_details(frame: ImageBGR, view: ReviewView) -> None:
    """Escribe bajo el recorte los datos del avistamiento y la ayuda de teclas."""
    record = view.record
    y = MARGIN + CROP_AREA_HEIGHT + _LINE_STEP
    _draw_text(
        frame,
        f"#{record.sighting_id}  lectura: {record.plate_text}",
        (MARGIN, y),
        ACCENT_COLOR,
        1.0,
        2,
    )
    y += _LINE_STEP
    _draw_text(
        frame,
        f"tipo: {record.vehicle_type}   confianza: {record.confidence:.2f}   "
        f"acuerdo: {record.agreement:.2f}   lecturas: {record.num_readings}",
        (MARGIN, y),
        TEXT_COLOR,
        0.65,
        1,
    )
    y += _LINE_STEP
    reasons = ", ".join(reason.value for reason in record.reasons) or "-"
    _draw_text(frame, f"razones: {reasons}", (MARGIN, y), MUTED_COLOR, 0.6, 1)
    y += _LINE_STEP
    _draw_prompt(frame, view, y)


def _draw_prompt(frame: ImageBGR, view: ReviewView, y: int) -> None:
    """Escribe las teclas disponibles y, si procede, el mensaje de error."""
    if view.typed is None:
        text, color = MENU_TEXT, TEXT_COLOR
    else:
        text, color = f"corregir: {view.typed}_   {EDIT_HINT}", ACCENT_COLOR
    _draw_text(frame, text, (MARGIN, y), color, 0.7, 2)
    if view.message is not None:
        _draw_text(frame, view.message, (MARGIN, y + _LINE_STEP), ERROR_COLOR, 0.65, 2)


def _draw_text(
    frame: ImageBGR,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    scale: float,
    thickness: int,
) -> None:
    """Escribe un texto antialias con la fuente Hershey del lienzo."""
    cv2.putText(frame, text, origin, _FONT, scale, color, thickness, cv2.LINE_AA)


class OpenCvReviewUI:
    """Presenta cada avistamiento y recoge la decisión del operador en la ventana."""

    def __init__(self, window: WindowBackend | None = None, poll_ms: int = POLL_MS) -> None:
        """Crea la interfaz sobre una ventana; por defecto usa una ventana OpenCV real.

        Args:
            window: backend de ventana; si es `None` se usa `OpenCvWindow`.
            poll_ms: milisegundos que cada vuelta espera una tecla.
        """
        self._window: WindowBackend = window if window is not None else OpenCvWindow()
        self._poll_ms = poll_ms

    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision:
        """Muestra un avistamiento y recoge la decisión del operador.

        Args:
            record: avistamiento persistido que se presenta.
            crop: recorte de placa, o `None` si no está disponible.

        Returns:
            Decisión del operador para ese avistamiento.
        """
        typed: str | None = None
        message: str | None = None
        while True:
            if not self._window.is_open():
                return ReviewDecision(ReviewAction.QUIT)
            self._window.show(render_review_frame(ReviewView(record, crop, typed, message)))
            key = self._window.wait_key(self._poll_ms)
            if key < 0:
                continue
            decision: ReviewDecision | None
            if typed is None:
                typed, message, decision = self._handle_menu_key(key & 0xFF)
            else:
                typed, message, decision = self._handle_edit_key(key & 0xFF, typed, message)
            if decision is not None:
                return decision

    def close(self) -> None:
        """Cierra la ventana de revisión."""
        self._window.close()

    def _handle_menu_key(self, code: int) -> tuple[str | None, str | None, ReviewDecision | None]:
        """Procesa una tecla en modo menú."""
        char = chr(code).lower()
        if char == "e":
            return "", None, None
        if code == KEY_ESC:
            return None, None, ReviewDecision(ReviewAction.QUIT)
        action = KEY_TO_ACTION.get(char)
        if action is None:
            return None, INVALID_KEY, None
        return None, None, ReviewDecision(action)

    def _handle_edit_key(
        self, code: int, typed: str, message: str | None
    ) -> tuple[str | None, str | None, ReviewDecision | None]:
        """Procesa una tecla en modo edición."""
        if code == KEY_ESC:
            return None, None, None
        if code in KEYS_ENTER:
            return _confirm_edit(typed)
        if code in KEYS_BACKSPACE:
            return typed[:-1], message, None
        typed, message = _append_char(typed, code, message)
        return typed, message, None


def _confirm_edit(typed: str) -> tuple[str | None, str | None, ReviewDecision | None]:
    """Acepta el texto escrito si es una placa válida o marca el error."""
    if PLATE_TEXT_REGEX.fullmatch(typed) is not None:
        return typed, None, ReviewDecision(ReviewAction.CORRECT, typed)
    return typed, INVALID_TEXT, None


def _append_char(typed: str, code: int, message: str | None) -> tuple[str, str | None]:
    """Añade un carácter alfanumérico si cabe; si no, deja el texto como estaba."""
    char = chr(code).upper()
    if _is_plate_char(char) and len(typed) < MAX_PLATE_CHARS:
        return typed + char, None
    return typed, message


def _is_plate_char(char: str) -> bool:
    """Indica si el carácter pertenece a `A-Z` o `0-9`."""
    return "A" <= char <= "Z" or "0" <= char <= "9"
