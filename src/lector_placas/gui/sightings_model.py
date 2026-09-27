"""Modelo de tabla de solo lectura para los avistamientos de la pestaña "Avistamientos"."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

from lector_placas.domain.entities import SightingRecord
from lector_placas.gui.labels import STATUS_LABELS, VEHICLE_LABELS, local_datetime, percent

SIGHTING_COLUMNS: Final[tuple[str, ...]] = (
    "ID",
    "Fecha",
    "Corrida",
    "Tipo",
    "Placa",
    "OCR",
    "Estado",
    "Confianza",
    "Lecturas",
    "Razones",
)
_NUMERIC_COLUMNS: Final[frozenset[int]] = frozenset({0, 2, 7, 8})


def _cell_text(record: SightingRecord, column: int) -> str:
    """Devuelve el texto de la celda de `record` en la columna `column`."""
    reasons = ", ".join(reason.value for reason in record.reasons) or "-"
    values = (
        str(record.sighting_id),
        local_datetime(record.created_at),
        str(record.run_id),
        VEHICLE_LABELS[record.vehicle_type],
        record.plate_text,
        record.ocr_text,
        STATUS_LABELS[record.status],
        percent(record.confidence),
        str(record.num_readings),
        reasons,
    )
    return values[column]


class SightingsTableModel(QAbstractTableModel):
    """Modelo de tabla de solo lectura con una fila por `SightingRecord`."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Crea un modelo vacío.

        Args:
            parent: objeto padre del modelo.
        """
        super().__init__(parent)
        self._records: tuple[SightingRecord, ...] = ()

    def set_records(self, records: Sequence[SightingRecord]) -> None:
        """Reemplaza los avistamientos mostrados por `records`."""
        self.beginResetModel()
        self._records = tuple(records)
        self.endResetModel()

    def record_at(self, row: int) -> SightingRecord:
        """Devuelve el avistamiento de la fila `row`."""
        return self._records[row]

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de filas (una por avistamiento)."""
        return len(self._records)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de columnas, fijo e igual a `SIGHTING_COLUMNS`."""
        return len(SIGHTING_COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | int | None:
        """Texto o alineación de la celda `index`."""
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return _cell_text(self._records[index.row()], index.column())
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in _NUMERIC_COLUMNS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Título de la columna `section` en orientación horizontal."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return SIGHTING_COLUMNS[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Solo lectura: las celdas se pueden seleccionar pero no editar."""
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
