"""Modelo de tabla de solo lectura para las corridas de la pestaña "Procesar"."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

from lector_placas.application.ports import RunRecord
from lector_placas.gui.labels import RUN_STATUS_LABELS, local_datetime

RUN_COLUMNS: Final[tuple[str, ...]] = (
    "Corrida",
    "Inicio",
    "Perfil",
    "Estado",
    "Duración",
    "Confirmadas",
    "Sin verificar",
    "Sin lectura",
    "Velocidad",
)
NOT_AVAILABLE: Final[str] = "n/d"


def _format_duration(duration_ms: int | None) -> str:
    """Formatea una duración de video en `mm:ss` o `n/d` si se desconoce."""
    if duration_ms is None:
        return NOT_AVAILABLE
    minutes, seconds = divmod(duration_ms // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_count(value: int | None) -> str:
    """Formatea un conteo entero o `n/d` si se desconoce."""
    return NOT_AVAILABLE if value is None else str(value)


def _format_velocity(duration_ms: int | None, processing_ms: int | None) -> str:
    """Formatea la velocidad de procesamiento como `d.dd x` o `n/d` si falta algún dato."""
    if duration_ms is None or processing_ms is None or processing_ms == 0:
        return NOT_AVAILABLE
    return f"{duration_ms / processing_ms:.2f}x"


def _cell_text(run: RunRecord, column: int) -> str:
    """Devuelve el texto de la celda de `run` en la columna `column`."""
    values = (
        str(run.run_id),
        local_datetime(run.started_at),
        run.profile,
        RUN_STATUS_LABELS[run.status],
        _format_duration(run.duration_ms),
        _format_count(run.sightings_confirmed),
        _format_count(run.sightings_unverified),
        _format_count(run.tracks_without_reading),
        _format_velocity(run.duration_ms, run.processing_ms),
    )
    return values[column]


class RunsTableModel(QAbstractTableModel):
    """Modelo de tabla de solo lectura con una fila por `RunRecord`."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Crea un modelo vacío.

        Args:
            parent: objeto padre del modelo.
        """
        super().__init__(parent)
        self._runs: tuple[RunRecord, ...] = ()

    def set_runs(self, runs: Sequence[RunRecord]) -> None:
        """Reemplaza las corridas mostradas por `runs`."""
        self.beginResetModel()
        self._runs = tuple(runs)
        self.endResetModel()

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de filas (una por corrida)."""
        return len(self._runs)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        """Número de columnas, fijo e igual a `RUN_COLUMNS`."""
        return len(RUN_COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Texto de la celda `index` para el rol de visualización."""
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        return _cell_text(self._runs[index.row()], index.column())

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Título de la columna `section` en orientación horizontal."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return RUN_COLUMNS[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Solo lectura: las celdas se pueden seleccionar pero no editar."""
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
