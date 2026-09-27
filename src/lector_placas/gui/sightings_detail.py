"""Widget de detalle de un avistamiento: recorte descifrado y datos de aparición/revisión."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lector_placas.application.ports import CropStore, ImageBGR
from lector_placas.domain.entities import SightingRecord
from lector_placas.domain.errors import CropNotFoundError, CropStoreError, EncryptionError
from lector_placas.gui.images import bgr_to_qimage
from lector_placas.gui.labels import local_datetime, video_time

NO_CROP_TEXT: Final[str] = "sin recorte"
CROP_PURGED_TEXT: Final[str] = "recorte no disponible (purgado)"
CROP_ERROR_TEXT: Final[str] = "no se pudo leer el recorte"
NOT_REVIEWED_TEXT: Final[str] = "sin revisar"
CROP_WIDTH: Final[int] = 480
CROP_HEIGHT: Final[int] = 160


def _detail_text(record: SightingRecord) -> str:
    """Compone el texto de detalle de `record` (aparición, revisión y formatos)."""
    reviewed = (
        local_datetime(record.reviewed_at) if record.reviewed_at is not None else NOT_REVIEWED_TEXT
    )
    formats = ", ".join(record.format_ids) or "-"
    return (
        f"aparición: {video_time(record.first_seen_ms)}-{video_time(record.last_seen_ms)}\n"
        f"revisado: {reviewed}\n"
        f"formatos: {formats}"
    )


class SightingsDetail(QWidget):
    """Recorte y datos de aparición/revisión del avistamiento seleccionado en la tabla."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea el widget de detalle, vacío.

        Args:
            parent: widget padre, o `None`.
        """
        super().__init__(parent)
        self._crop_label = QLabel(self)
        self._crop_label.setFixedSize(CROP_WIDTH, CROP_HEIGHT)
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label = QLabel(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._crop_label)
        layout.addWidget(self._text_label)

    def clear(self) -> None:
        """Descarta el recorte y el texto mostrados."""
        self._crop_label.setPixmap(QPixmap())
        self._crop_label.setText("")
        self._text_label.setText("")

    def show_record(self, record: SightingRecord, crop_store: CropStore) -> None:
        """Muestra los datos de `record` y su recorte, cargado desde `crop_store`.

        Args:
            record: avistamiento seleccionado.
            crop_store: almacén desde el que se descifra el recorte, si tiene uno.
        """
        self._text_label.setText(_detail_text(record))
        self._show_crop(record.crop_ref, crop_store)

    def _show_crop(self, crop_ref: str | None, crop_store: CropStore) -> None:
        """Carga y muestra el recorte de `crop_ref`, o el texto que explica por qué no hay."""
        if crop_ref is None:
            self._crop_label.setText(NO_CROP_TEXT)
            return
        try:
            crop = crop_store.load(crop_ref)
        except CropNotFoundError:
            self._crop_label.setText(CROP_PURGED_TEXT)
            return
        except (CropStoreError, EncryptionError):
            self._crop_label.setText(CROP_ERROR_TEXT)
            return
        self._set_pixmap(crop)

    def _set_pixmap(self, crop: ImageBGR) -> None:
        """Escala y muestra el recorte descifrado, conservando su proporción."""
        pixmap = QPixmap.fromImage(bgr_to_qimage(crop)).scaled(
            CROP_WIDTH,
            CROP_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_label.setPixmap(pixmap)
