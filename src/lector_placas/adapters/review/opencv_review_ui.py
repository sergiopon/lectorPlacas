"""Interfaz de revisión por terminal con el recorte ampliado en una ventana OpenCV."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

import cv2

from lector_placas.application.ports import ImageBGR, ReviewAction, ReviewDecision
from lector_placas.domain.entities import PLATE_TEXT_REGEX, SightingRecord

WINDOW_NAME: Final[str] = "lector-placas: revision"
SCALE: Final[int] = 3
PROMPT: Final[str] = "[c]onfirmar  [e]ditar  [r]echazar  [s]altar  [q]salir: "
CORRECTION_PROMPT: Final[str] = "texto corregido: "
INVALID_OPTION: Final[str] = "opción inválida\n"
INVALID_TEXT: Final[str] = "texto inválido\n"
KEY_TO_ACTION: Final[Mapping[str, ReviewAction]] = MappingProxyType(
    {
        "c": ReviewAction.CONFIRM,
        "e": ReviewAction.CORRECT,
        "r": ReviewAction.REJECT,
        "s": ReviewAction.SKIP,
        "q": ReviewAction.QUIT,
    }
)


class OpenCvReviewUI:
    """Muestra el recorte ampliado de cada avistamiento y lee la decisión por terminal."""

    def __init__(
        self,
        read_line: Callable[[str], str] = input,
        write: Callable[[str], object] = sys.stdout.write,
        show: bool = True,
    ) -> None:
        """Crea la interfaz de revisión.

        Args:
            read_line: función que pide una línea al operador.
            write: función que escribe la salida dirigida al operador.
            show: si es `True`, abre una ventana con el recorte ampliado.
        """
        self._read_line = read_line
        self._write = write
        self._show = show

    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision:
        """Muestra un avistamiento y recoge la decisión del operador.

        Args:
            record: avistamiento persistido que se presenta.
            crop: recorte de placa, o `None` si no está disponible.

        Returns:
            Decisión del operador para ese avistamiento.

        Raises:
            ReviewError: si falla la interacción con el operador.
        """
        self._show_crop(crop)
        self._write(_describe(record))
        while True:
            answer = self._read_line_or_none(PROMPT)
            if answer is None:
                return ReviewDecision(ReviewAction.QUIT)
            action = KEY_TO_ACTION.get(answer.strip().lower())
            if action is None:
                self._write(INVALID_OPTION)
            elif action is not ReviewAction.CORRECT:
                return ReviewDecision(action)
            else:
                decision = self._ask_correction()
                if decision is not None:
                    return decision

    def close(self) -> None:
        """Cierra la ventana de revisión si se estaba mostrando."""
        if not self._show:
            return
        with contextlib.suppress(cv2.error):
            cv2.destroyWindow(WINDOW_NAME)

    def _show_crop(self, crop: ImageBGR | None) -> None:
        """Muestra el recorte ampliado en la ventana, si procede."""
        if not self._show or crop is None:
            return
        enlarged = cv2.resize(crop, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)
        cv2.imshow(WINDOW_NAME, enlarged)
        cv2.waitKey(1)

    def _read_line_or_none(self, prompt: str) -> str | None:
        """Lee una línea del operador; `None` si la entrada se agotó."""
        try:
            return self._read_line(prompt)
        except EOFError:
            return None

    def _ask_correction(self) -> ReviewDecision | None:
        """Pide el texto corregido; `None` si el operador vuelve al menú principal."""
        while True:
            answer = self._read_line_or_none(CORRECTION_PROMPT)
            if answer is None:
                return ReviewDecision(ReviewAction.QUIT)
            text = answer.strip().upper()
            if not text:
                return None
            if PLATE_TEXT_REGEX.fullmatch(text) is not None:
                return ReviewDecision(ReviewAction.CORRECT, text)
            self._write(INVALID_TEXT)


def _describe(record: SightingRecord) -> str:
    """Compone la línea que resume el avistamiento para el operador."""
    reasons = ",".join(record.reasons)
    return (
        f"#{record.sighting_id} lectura={record.plate_text} "
        f"confianza={record.confidence:.2f} acuerdo={record.agreement:.2f} "
        f"lecturas={record.num_readings} tipo={record.vehicle_type} razones={reasons}\n"
    )
