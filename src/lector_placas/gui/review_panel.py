"""Panel lateral para revisar la placa elegida (spec 048, ADR-015)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.ports import ImageBGR, ReviewAction, ReviewDecision
from lector_placas.domain.entities import PLATE_TEXT_REGEX, ReviewStatus, SightingRecord
from lector_placas.gui.card_grid import EmptyState
from lector_placas.gui.images import bgr_to_pixmap
from lector_placas.gui.labels import (
    REASON_TEXTS,
    STATUS_BADGES,
    VEHICLE_LABELS,
    format_plate,
    percent,
    short_time,
)
from lector_placas.gui.theme import STATUS_COLORS, SURFACE

PANEL_WIDTH: Final[int] = 380
PANEL_CROP_BOX: Final[tuple[int, int]] = (340, 120)
EMPTY_TITLE: Final[str] = "Elige una placa"
EMPTY_HINT: Final[str] = "Haz clic en una tarjeta para verla en grande y revisarla."
CONFIDENCE_MAX: Final[int] = 100


class ReviewPanel(QFrame):
    """Muestra la placa elegida en grande y decide sobre ella sin diálogos modales."""

    decided = Signal(object)
    skip_requested = Signal()

    # Asignados por los constructores de módulo `_build_*` (clase ≤ 150 líneas, ARQUITECTURA §6).
    _empty: EmptyState
    _body: QWidget
    _stack: QStackedWidget
    _crop_label: QLabel
    _plate_label: QLabel
    _status_label: QLabel
    _ocr_label: QLabel
    _confidence_bar: QProgressBar
    _reasons_title: QLabel
    _reasons_label: QLabel
    _meta_label: QLabel
    _actions: QWidget
    _buttons: tuple[QPushButton, ...]
    _note_label: QLabel
    _editor: QWidget
    _edit: QLineEdit
    _error_label: QLabel

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea el panel vacío, con el aviso de elegir una placa."""
        super().__init__(parent)
        self.setObjectName("ReviewPanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.setStyleSheet(f"QFrame#ReviewPanel {{ background: {SURFACE}; }}")
        self._record: SightingRecord | None = None
        self._editing = False
        self._enabled = True
        self._empty = EmptyState(self)
        self._empty.set_message(EMPTY_TITLE, EMPTY_HINT)
        self._body = body = QWidget(self)
        _build_body(body, self)
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._empty)
        self._stack.addWidget(body)
        _set_editing(self, False)
        self.set_actions_enabled(True)
        self._stack.setCurrentWidget(self._empty)

    def show_record(
        self, record: SightingRecord, crop: ImageBGR | None, crop_note: str | None
    ) -> None:
        """Presenta `record`, su recorte (o `crop_note`) y sus acciones."""
        self._record = record
        _set_editing(self, False)
        _apply_record(self, record, crop, crop_note)
        self._stack.setCurrentWidget(self._body)

    def clear(self) -> None:
        """Vuelve al aviso vacío, sin ningún registro cargado."""
        self._record = None
        _set_editing(self, False)
        self._stack.setCurrentWidget(self._empty)

    def set_actions_enabled(self, enabled: bool) -> None:
        """Habilita o deshabilita las acciones y muestra la nota de espera."""
        self._enabled = enabled
        for button in self._buttons:
            button.setEnabled(enabled)
        self._note_label.setVisible(not enabled)

    def is_editing(self) -> bool:
        """Indica si el panel está en modo de corrección del texto."""
        return self._editing

    def confirm(self) -> None:
        """Emite `decided(CONFIRM)` si hay un registro y se puede decidir."""
        if self._can_decide():
            self.decided.emit(ReviewDecision(ReviewAction.CONFIRM))

    def start_edit(self) -> None:
        """Entra en modo de corrección con el texto vigente seleccionado."""
        if self._can_decide():
            _set_editing(self, True)

    def reject(self) -> None:
        """Emite `decided(REJECT)` si hay un registro y se puede decidir."""
        if self._can_decide():
            self.decided.emit(ReviewDecision(ReviewAction.REJECT))

    def skip(self) -> None:
        """Emite `skip_requested` si hay un registro y se puede decidir."""
        if self._can_decide():
            self.skip_requested.emit()

    def cancel_edit(self) -> None:
        """Abandona la corrección sin emitir ninguna decisión."""
        if self._editing:
            _set_editing(self, False)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (nombre Qt)
        """Cancela la edición con Esc; el resto de eventos van a la implementación base."""
        if (
            self._editing
            and watched is self._edit
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            self.cancel_edit()
            return True
        return super().eventFilter(watched, event)

    def _can_decide(self) -> bool:
        return self._record is not None and self._enabled and not self._editing

    def _on_text_changed(self, text: str) -> None:
        if text != text.upper():
            self._edit.setText(text.upper())
            self._edit.setCursorPosition(len(text.upper()))

    def _save_edit(self) -> None:
        if not self._editing or self._record is None:
            return
        text = self._edit.text()
        if PLATE_TEXT_REGEX.fullmatch(text) is None:
            self._error_label.setText("Escribe solo letras y números (1 a 10)")
            return
        decision = (
            ReviewDecision(ReviewAction.CONFIRM)
            if text == self._record.plate_text
            else ReviewDecision(ReviewAction.CORRECT, text)
        )
        _set_editing(self, False)
        self.decided.emit(decision)


def _build_body(body: QWidget, panel: ReviewPanel) -> None:
    panel._crop_label = QLabel(body)
    panel._crop_label.setFixedSize(*PANEL_CROP_BOX)
    panel._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    panel._plate_label, panel._status_label = QLabel(body), QLabel(body)
    panel._plate_label.setObjectName("PlateText")
    panel._ocr_label, panel._reasons_title = QLabel(body), QLabel("Por qué revisarla", body)
    panel._reasons_label, panel._meta_label = QLabel(body), QLabel(body)
    panel._meta_label.setProperty("role", "muted")
    panel._meta_label.setWordWrap(True)
    panel._reasons_label.setWordWrap(True)
    panel._confidence_bar = QProgressBar(body)
    panel._confidence_bar.setRange(0, CONFIDENCE_MAX)
    panel._actions, panel._buttons, panel._note_label = _make_actions(body, panel)
    panel._editor, panel._edit, panel._error_label = _make_editor(body, panel)
    layout = QVBoxLayout(body)
    top = (
        panel._crop_label,
        panel._plate_label,
        panel._status_label,
        panel._ocr_label,
        QLabel("Seguridad del lector", body),
        panel._confidence_bar,
        panel._reasons_title,
        panel._reasons_label,
        panel._meta_label,
    )
    for widget in top:
        layout.addWidget(widget)
    layout.addStretch(1)
    layout.addWidget(panel._actions)
    layout.addWidget(panel._editor)


def _make_button(
    parent: QWidget, text: str, slot: Callable[[], None], role: str | None = None
) -> QPushButton:
    button = QPushButton(text, parent)
    if role is not None:
        button.setProperty("role", role)
    button.clicked.connect(slot)
    return button


def _make_actions(
    parent: QWidget, panel: ReviewPanel
) -> tuple[QWidget, tuple[QPushButton, ...], QLabel]:
    specs = (
        ("✓ Es correcta   C", panel.confirm, "primary"),
        ("✎ Corregir   E", panel.start_edit, None),
        ("✗ No es una placa   R", panel.reject, None),
        ("Saltar   S", panel.skip, "ghost"),
    )
    buttons = tuple(_make_button(parent, text, slot, role) for text, slot, role in specs)
    note = QLabel("Espera a que termine el procesamiento para revisar.", parent)
    note.setProperty("role", "muted")
    note.setWordWrap(True)
    container, layout = _column(parent)
    for button in buttons:
        layout.addWidget(button)
    layout.addWidget(note)
    return container, buttons, note


def _make_editor(parent: QWidget, panel: ReviewPanel) -> tuple[QWidget, QLineEdit, QLabel]:
    edit = QLineEdit(parent)
    edit.setMaxLength(10)
    edit.setValidator(QRegularExpressionValidator("^[A-Za-z0-9]{0,10}$", parent))
    edit.installEventFilter(panel)
    edit.textChanged.connect(panel._on_text_changed)
    edit.returnPressed.connect(panel._save_edit)
    row = QHBoxLayout()
    row.addWidget(edit)
    row.addWidget(_make_button(parent, "Guardar   Enter", panel._save_edit, "primary"))
    row.addWidget(_make_button(parent, "Cancelar   Esc", panel.cancel_edit))
    error = QLabel(parent)
    error.setStyleSheet(f"color: {STATUS_COLORS[ReviewStatus.REJECTED][0]};")
    container, layout = _column(parent)
    layout.addLayout(row)
    layout.addWidget(error)
    return container, edit, error


def _column(parent: QWidget) -> tuple[QWidget, QVBoxLayout]:
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    return container, layout


def _set_editing(panel: ReviewPanel, editing: bool) -> None:
    panel._editing = editing
    panel._error_label.clear()
    panel._actions.setVisible(not editing)
    panel._editor.setVisible(editing)
    record = panel._record if editing else None
    panel._edit.setText("" if record is None else record.plate_text)
    if record is not None:
        panel._edit.selectAll()
        panel._edit.setFocus()


def _apply_record(
    panel: ReviewPanel, record: SightingRecord, crop: ImageBGR | None, crop_note: str | None
) -> None:
    if crop is None:
        panel._crop_label.setPixmap(QPixmap())
        panel._crop_label.setText(crop_note if crop_note is not None else "sin imagen")
    else:
        panel._crop_label.setText("")
        panel._crop_label.setPixmap(bgr_to_pixmap(crop, *PANEL_CROP_BOX))
    panel._plate_label.setText(format_plate(record.plate_text))
    foreground, background = STATUS_COLORS[record.status]
    panel._status_label.setText(STATUS_BADGES[record.status])
    panel._status_label.setStyleSheet(
        f"color: {foreground}; background: {background}; border-radius: 9px; padding: 2px 8px;"
    )
    panel._ocr_label.setVisible(record.ocr_text != record.plate_text)
    panel._ocr_label.setText(f"El sistema leyó: {format_plate(record.ocr_text)}")
    panel._confidence_bar.setValue(round(record.confidence * CONFIDENCE_MAX))
    panel._confidence_bar.setFormat(percent(record.confidence))
    panel._reasons_title.setVisible(bool(record.reasons))
    panel._reasons_label.setText("\n".join(f"• {REASON_TEXTS[r]}" for r in record.reasons))
    vehicle = VEHICLE_LABELS[record.vehicle_type].capitalize()
    first, last = short_time(record.first_seen_ms), short_time(record.last_seen_ms)
    panel._meta_label.setText(f"{vehicle} · aparece en {first}–{last} · video {record.run_id}")  # noqa: RUF001
