"""Diálogo Qt de revisión de un avistamiento (ADR-015, mismas teclas que la spec 034)."""

from __future__ import annotations

import re
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ImageBGR, ReviewAction, ReviewDecision
from lector_placas.domain.entities import PLATE_TEXT_REGEX, SightingRecord
from lector_placas.gui.images import bgr_to_qimage
from lector_placas.gui.labels import STATUS_LABELS, VEHICLE_LABELS, percent

REVIEW_TITLE: Final[str] = "Revisión"
INVALID_TEXT: Final[str] = "texto inválido"
NO_CROP_TEXT: Final[str] = "sin recorte"
CURRENT_TEXT_LABEL: Final[str] = "Texto actual"
MAX_CROP_WIDTH: Final[int] = 640
MAX_CROP_HEIGHT: Final[int] = 220
MAX_PLATE_CHARS: Final[int] = 10
_PLATE_CHAR_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]$")

_MENU_ACTIONS: Final[dict[int, ReviewAction]] = {
    int(Qt.Key.Key_C): ReviewAction.CONFIRM,
    int(Qt.Key.Key_R): ReviewAction.REJECT,
    int(Qt.Key.Key_S): ReviewAction.SKIP,
    int(Qt.Key.Key_Escape): ReviewAction.QUIT,
}


class _EditState:
    """Texto en edición del diálogo: escritura, borrado y validación contra el original."""

    def __init__(self) -> None:
        """Crea el estado con el texto en edición vacío."""
        self.typed = ""

    def reset(self) -> None:
        """Vacía el texto en edición."""
        self.typed = ""

    def backspace(self) -> None:
        """Borra el último carácter escrito, si hay alguno."""
        self.typed = self.typed[:-1]

    def append(self, text: str) -> bool:
        """Añade `text` en mayúscula si es un único carácter válido y cabe en el máximo.

        Returns:
            `True` si lo añadió; `False` si lo descartó.
        """
        if len(text) != 1 or len(self.typed) >= MAX_PLATE_CHARS:
            return False
        char = text.upper()
        if _PLATE_CHAR_REGEX.fullmatch(char) is None:
            return False
        self.typed += char
        return True

    def confirm(self, original: str) -> ReviewDecision | None:
        """Valida el texto en edición contra `original`.

        Returns:
            `ReviewDecision(CONFIRM)` si coincide con `original`, `ReviewDecision(CORRECT, …)`
            si es una placa válida distinta, o `None` si no cumple `PLATE_TEXT_REGEX`.
        """
        if PLATE_TEXT_REGEX.fullmatch(self.typed) is None:
            return None
        if self.typed == original:
            return ReviewDecision(ReviewAction.CONFIRM)
        return ReviewDecision(ReviewAction.CORRECT, self.typed)


class ReviewDialog(QDialog):
    """Diálogo modal que presenta un avistamiento y devuelve la decisión del operador."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Construye el diálogo, todavía sin ningún avistamiento cargado (`parent` opcional)."""
        super().__init__(parent)
        self.setWindowTitle(REVIEW_TITLE)
        self.setModal(True)
        self._record: SightingRecord | None = None
        self._decision: ReviewDecision | None = None
        self._editing = False
        self._edit = _EditState()
        self._build_ui()

    def present(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision:
        """Muestra `record` y su recorte en un diálogo modal y espera la decisión.

        Args:
            record: avistamiento a presentar.
            crop: recorte de placa ya descifrado, o `None` si no hay.

        Returns:
            La decisión tomada por el operador.
        """
        self._reset_state(record)
        self._set_crop(crop)
        self._info_label.setText(_info_text(record))
        self.exec()
        return self._decision if self._decision is not None else ReviewDecision(ReviewAction.QUIT)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Enruta `event` al modo menú o al modo edición."""
        if self._editing:
            self._handle_edit_key(event)
        else:
            self._handle_menu_key(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Trata el cierre de la ventana (aspa) como `QUIT` si no hay decisión aún."""
        if self._decision is None:
            self._decision = ReviewDecision(ReviewAction.QUIT)
        event.accept()

    def _build_ui(self) -> None:
        """Crea y arma los widgets del diálogo."""
        self._crop_label = QLabel(self)
        self._crop_label.setFixedSize(MAX_CROP_WIDTH, MAX_CROP_HEIGHT)
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label = QLabel(self)
        self._text_edit = QLineEdit(self)
        self._text_edit.setReadOnly(True)
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._message_label = QLabel(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._crop_label)
        layout.addWidget(self._info_label)
        layout.addWidget(QLabel(CURRENT_TEXT_LABEL, self))
        layout.addWidget(self._text_edit)
        layout.addWidget(self._message_label)
        layout.addLayout(_build_buttons(self))

    def _reset_state(self, record: SightingRecord) -> None:
        """Reinicia el estado del diálogo para presentar `record`."""
        self._record = record
        self._decision = None
        self._editing = False
        self._edit.reset()
        self._message_label.clear()
        self._text_edit.setReadOnly(True)
        self._text_edit.setText(record.plate_text)

    def _set_crop(self, crop: ImageBGR | None) -> None:
        """Muestra el recorte escalado, o el texto de reemplazo si no hay ninguno."""
        if crop is None:
            self._crop_label.setPixmap(QPixmap())
            self._crop_label.setText(NO_CROP_TEXT)
            return
        pixmap = QPixmap.fromImage(bgr_to_qimage(crop)).scaled(
            MAX_CROP_WIDTH,
            MAX_CROP_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_label.setText("")
        self._crop_label.setPixmap(pixmap)

    def _handle_menu_key(self, event: QKeyEvent) -> None:
        """Procesa una tecla en modo menú; cualquier tecla no reconocida no hace nada."""
        key = event.key()
        if key in _MENU_ACTIONS:
            self._finish(_MENU_ACTIONS[key])
        elif key == Qt.Key.Key_E:
            self._enter_edit_mode()

    def _enter_edit_mode(self) -> None:
        """Entra en modo edición con el campo de texto vacío."""
        self._editing = True
        self._edit.reset()
        self._message_label.clear()
        self._text_edit.setReadOnly(False)
        self._text_edit.setText(self._edit.typed)

    def _handle_edit_key(self, event: QKeyEvent) -> None:
        """Procesa una tecla en modo edición."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._exit_edit_mode()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_edit()
        elif key == Qt.Key.Key_Backspace:
            self._edit.backspace()
            self._text_edit.setText(self._edit.typed)
        elif self._edit.append(event.text()):
            self._text_edit.setText(self._edit.typed)

    def _exit_edit_mode(self) -> None:
        """Vuelve al modo menú restaurando el texto vigente del avistamiento."""
        record = self._record
        self._editing = False
        self._edit.reset()
        self._message_label.clear()
        self._text_edit.setReadOnly(True)
        if record is not None:
            self._text_edit.setText(record.plate_text)

    def _confirm_edit(self) -> None:
        """Valida el texto escrito y termina el diálogo, o muestra el error y sigue editando."""
        record = self._record
        decision = self._edit.confirm(record.plate_text) if record is not None else None
        if decision is None:
            self._message_label.setText(INVALID_TEXT)
            return
        self._finish(decision.action, decision.corrected_text)

    def _finish(self, action: ReviewAction, corrected_text: str | None = None) -> None:
        """Fija la decisión y cierra el diálogo."""
        self._decision = ReviewDecision(action, corrected_text)
        self.accept()


def _build_buttons(dialog: ReviewDialog) -> QHBoxLayout:
    """Crea los cinco botones de `dialog`, sin foco propio ni botón por defecto."""

    def make_button(label: str) -> QPushButton:
        button = QPushButton(label, dialog)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoDefault(False)
        button.setDefault(False)
        return button

    layout = QHBoxLayout()
    confirm_button = make_button("Confirmar [C]")
    confirm_button.clicked.connect(lambda: dialog._finish(ReviewAction.CONFIRM))
    layout.addWidget(confirm_button)
    edit_button = make_button("Editar [E]")
    edit_button.clicked.connect(dialog._enter_edit_mode)
    layout.addWidget(edit_button)
    for label, action in (
        ("Rechazar [R]", ReviewAction.REJECT),
        ("Saltar [S]", ReviewAction.SKIP),
        ("Salir [Esc]", ReviewAction.QUIT),
    ):
        button = make_button(label)
        button.clicked.connect(lambda checked=False, a=action: dialog._finish(a))
        layout.addWidget(button)
    return layout


class QtReviewUI:
    """Implementa `ReviewUI` reutilizando un único `ReviewDialog` perezoso."""

    def __init__(self, parent: QWidget | None) -> None:
        """Guarda el padre del diálogo, que se crea en el primer `ask`.

        Args:
            parent: widget padre del diálogo, o `None`.
        """
        self._parent = parent
        self._dialog: ReviewDialog | None = None

    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision:
        """Presenta `record` en el diálogo, creándolo la primera vez.

        Args:
            record: avistamiento a presentar.
            crop: recorte de placa ya descifrado, o `None` si no hay.

        Returns:
            La decisión tomada por el operador.
        """
        if self._dialog is None:
            self._dialog = ReviewDialog(self._parent)
        return self._dialog.present(record, crop)

    def close(self) -> None:
        """Cierra y descarta el diálogo, si se llegó a crear. Idempotente."""
        if self._dialog is not None:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None


def _info_text(record: SightingRecord) -> str:
    """Compone el texto de datos del avistamiento (sin exponer el texto de placa más de una vez)."""
    reasons = ", ".join(reason.value for reason in record.reasons) or "-"
    return (
        f"#{record.sighting_id}  corrida {record.run_id}  "
        f"{VEHICLE_LABELS[record.vehicle_type]}  {STATUS_LABELS[record.status]}\n"
        f"Texto OCR: {record.ocr_text}\n"
        f"confianza: {percent(record.confidence)}  acuerdo: {percent(record.agreement)}  "
        f"lecturas: {record.num_readings}\n"
        f"razones: {reasons}"
    )
