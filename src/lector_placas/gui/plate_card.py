"""Tarjeta de placa: recorte, lectura grande y estado en color (spec 047, ADR-015)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lector_placas.domain.entities import SightingRecord
from lector_placas.domain.errors import InvalidEntityError
from lector_placas.gui.labels import STATUS_BADGES, VEHICLE_LABELS, format_plate, short_time
from lector_placas.gui.theme import STATUS_COLORS

CARD_WIDTH: Final[int] = 260
CARD_HEIGHT: Final[int] = 176
CROP_BOX: Final[tuple[int, int]] = (244, 84)
NO_IMAGE_TEXT: Final[str] = "sin imagen"

_BADGE_RADIUS: Final[int] = 9


class PlateCard(QFrame):
    """Tarjeta clicable con el recorte, la lectura vigente y el estado de un avistamiento."""

    clicked = Signal(int)

    def __init__(
        self, record: SightingRecord, crop: QPixmap | None, parent: QWidget | None = None
    ) -> None:
        """Construye la tarjeta de `record` con su recorte ya escalado.

        Args:
            record: avistamiento a mostrar.
            crop: recorte ya convertido a `QPixmap`, o `None` si no hay.
            parent: widget padre, o `None`.
        """
        super().__init__(parent)
        self.setObjectName("PlateCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", "false")
        self._record = record
        self._crop_label = QLabel(self)
        self._crop_label.setFixedSize(CROP_BOX[0], CROP_BOX[1])
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._plate_label = QLabel(self)
        self._plate_label.setObjectName("PlateText")
        self._status_label = QLabel(self)
        self._meta_label = QLabel(self)
        self._meta_label.setProperty("role", "muted")
        self._build_layout()
        self._apply_record(record)
        self._set_crop(crop)

    def sighting_id(self) -> int:
        """Devuelve el identificador del avistamiento que muestra la tarjeta."""
        return self._record.sighting_id

    def update_record(self, record: SightingRecord) -> None:
        """Actualiza lectura, estado y línea de datos; el recorte no cambia.

        Args:
            record: avistamiento actualizado, con el mismo `sighting_id`.

        Raises:
            InvalidEntityError: si `record.sighting_id` no es el de la tarjeta.
        """
        if record.sighting_id != self._record.sighting_id:
            raise InvalidEntityError("el avistamiento no corresponde a la tarjeta")
        self._record = record
        self._apply_record(record)

    def set_selected(self, selected: bool) -> None:
        """Marca o desmarca la tarjeta y repinta su borde.

        Args:
            selected: `True` para marcarla como seleccionada.
        """
        self.setProperty("selected", "true" if selected else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def is_selected(self) -> bool:
        """Indica si la tarjeta está marcada como seleccionada."""
        return bool(self.property("selected") == "true")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (nombre impuesto por Qt)
        """Emite `clicked` con el avistamiento ante un clic izquierdo.

        Args:
            event: evento de ratón.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._record.sighting_id)
        super().mousePressEvent(event)

    def _build_layout(self) -> None:
        """Arma el recorte centrado, la fila de lectura y estado y la línea de datos."""
        crop_row = QHBoxLayout()
        crop_row.addStretch(1)
        crop_row.addWidget(self._crop_label)
        crop_row.addStretch(1)
        plate_row = QHBoxLayout()
        plate_row.addWidget(self._plate_label)
        plate_row.addStretch(1)
        plate_row.addWidget(self._status_label)
        layout = QVBoxLayout(self)
        layout.addLayout(crop_row)
        layout.addLayout(plate_row)
        layout.addWidget(self._meta_label)
        layout.addStretch(1)

    def _apply_record(self, record: SightingRecord) -> None:
        """Escribe en las etiquetas la lectura, la insignia de estado y la línea de datos."""
        self._plate_label.setText(format_plate(record.plate_text))
        foreground, background = STATUS_COLORS[record.status]
        self._status_label.setText(STATUS_BADGES[record.status])
        self._status_label.setStyleSheet(
            f"color: {foreground}; background: {background};"
            f" border-radius: {_BADGE_RADIUS}px; padding: 2px 8px;"
        )
        self._meta_label.setText(
            f"{VEHICLE_LABELS[record.vehicle_type].capitalize()} ·"
            f" {short_time(record.first_seen_ms)} · {record.num_readings} lecturas"
        )

    def _set_crop(self, crop: QPixmap | None) -> None:
        """Muestra `crop` o el texto de reemplazo si no hay recorte."""
        if crop is None:
            self._crop_label.setPixmap(QPixmap())
            self._crop_label.setProperty("role", "muted")
            self._crop_label.setText(NO_IMAGE_TEXT)
            return
        self._crop_label.setText("")
        self._crop_label.setPixmap(crop)
