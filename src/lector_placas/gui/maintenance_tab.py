"""Pestaña "Exportar y retención": exportar CSV, purgar y ver métricas de la revisión (RF-36)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lector_placas.application.export_sightings import ExportSightings
from lector_placas.application.ports import PlateRepository
from lector_placas.cli import composition
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import (
    EvaluationError,
    ExportError,
    LectorPlacasError,
    RepositoryError,
)
from lector_placas.evaluation.review_metrics import ReviewMetrics, compute_review_metrics
from lector_placas.gui.labels import STATUS_LABELS, percent
from lector_placas.gui.session import GuiSession

__all__ = ["METRICS_PAGE_SIZE", "MaintenanceTab"]

METRICS_PAGE_SIZE: Final[int] = 500
DIALOG_TITLE: Final[str] = "lectorPlacas"
STATUS_ALL_LABEL: Final[str] = "Todos"
NOT_AVAILABLE: Final[str] = "n/d"
PURGE_CONFIRM_MESSAGE: Final[str] = "Se borrarán los datos vencidos según la retención. ¿Continuar?"
METRICS_NOTE: Final[str] = (
    "Estimación por muestreo sobre lo revisado; no sustituye la evaluación con ground truth "
    "(docs/04-evaluacion.md)"
)
# (etiqueta, campo de ReviewMetrics, si se formatea como tasa) en el orden que pide la spec.
_METRIC_ROWS: Final[tuple[tuple[str, str, bool], ...]] = (
    ("Confirmadas totales", "confirmed_total", False),
    ("Confirmadas auditadas", "confirmed_audited", False),
    ("Precisión de confirmadas", "precision_confirmed", True),
    ("Confirmadas mantenidas", "confirmed_kept", False),
    ("Confirmadas corregidas", "confirmed_corrected", False),
    ("Confirmadas rechazadas", "confirmed_rejected", False),
    ("Confirmadas borrosas", "confirmed_illegible", False),
    ("Sin verificar totales", "unverified_total", False),
    ("Sin verificar pendientes", "unverified_pending", False),
    ("Sin verificar confirmadas", "unverified_confirmed", False),
    ("Sin verificar corregidas", "unverified_corrected", False),
    ("Sin verificar rechazadas", "unverified_rejected", False),
    ("Sin verificar borrosas", "unverified_illegible", False),
    ("Lecturas revisadas", "reviewed_readings", False),
    ("CER", "cer", True),
    ("Coincidencia exacta", "exact_match_rate", True),
)


def _selected_status(combo: QComboBox) -> ReviewStatus | None:
    """Estado elegido en el combo de exportación, o `None` para "Todos"."""
    index = combo.currentIndex()
    if index == 0:
        return None
    return tuple(ReviewStatus)[index - 1]


def _collect_all(repository: PlateRepository) -> list[SightingRecord]:
    """Recorre todas las páginas de avistamientos, de cualquier estado."""
    records: list[SightingRecord] = []
    offset = 0
    while True:
        page = repository.list_sightings(None, METRICS_PAGE_SIZE, offset)
        records.extend(page)
        if len(page) < METRICS_PAGE_SIZE:
            return records
        offset += METRICS_PAGE_SIZE


def _format_metric(value: float | int | None, is_rate: bool) -> str:
    """Formatea un valor de `ReviewMetrics`: tasas con `percent`, o "n/d" si son `None`."""
    if is_rate:
        return NOT_AVAILABLE if value is None else percent(value)
    return str(value)


def _clear_reason_rows(form: QFormLayout) -> None:
    """Quita todas las filas del formulario de razones."""
    while form.rowCount():
        form.removeRow(0)


def _build_export_row(tab: MaintenanceTab) -> QHBoxLayout:
    """Crea el combo de estado, el botón de exportar y la etiqueta de resultado de `tab`."""
    tab._export_combo = QComboBox(tab)
    tab._export_combo.addItem(STATUS_ALL_LABEL)
    for status in ReviewStatus:
        tab._export_combo.addItem(STATUS_LABELS[status])
    tab._export_button = QPushButton("Exportar CSV", tab)
    tab._export_button.clicked.connect(tab.export)
    tab._export_label = QLabel(tab)
    layout = QHBoxLayout()
    layout.addWidget(tab._export_combo)
    layout.addWidget(tab._export_button)
    layout.addWidget(tab._export_label, 1)
    return layout


def _build_retention_column(tab: MaintenanceTab) -> QVBoxLayout:
    """Crea la etiqueta de política, el botón de purga y su resultado, de `tab`."""
    retention = tab._session.config.retention
    tab._retention_label = QLabel(
        f"Retención: recortes {retention.crops_days} días · registros {retention.records_days} días"
        f" · entrenamiento {retention.training_days} días",
        tab,
    )
    tab._purge_button = QPushButton("Purgar ahora", tab)
    tab._purge_button.clicked.connect(tab.purge)
    tab._purge_label = QLabel(tab)
    layout = QVBoxLayout()
    layout.addWidget(tab._retention_label)
    layout.addWidget(tab._purge_button)
    layout.addWidget(tab._purge_label)
    return layout


def _build_metric_labels(tab: QWidget, form: QFormLayout) -> dict[str, QLabel]:
    """Añade una fila por cada métrica fija y devuelve sus etiquetas por nombre de campo."""
    labels: dict[str, QLabel] = {}
    for text, field, _is_rate in _METRIC_ROWS:
        label = QLabel(tab)
        form.addRow(text, label)
        labels[field] = label
    return labels


def _build_metrics_section(tab: MaintenanceTab) -> QVBoxLayout:
    """Crea el botón de cálculo, el formulario de métricas y la nota fija, de `tab`."""
    tab._metrics_button = QPushButton("Calcular", tab)
    tab._metrics_button.clicked.connect(tab.compute_metrics)
    tab._metrics_message = QLabel(tab)
    tab._metrics_form = QFormLayout()
    tab._metric_labels = _build_metric_labels(tab, tab._metrics_form)
    tab._reason_form = QFormLayout()
    tab._reason_labels = {}
    note = QLabel(METRICS_NOTE, tab)
    note.setWordWrap(True)
    layout = QVBoxLayout()
    layout.addWidget(tab._metrics_button)
    layout.addWidget(tab._metrics_message)
    layout.addLayout(tab._metrics_form)
    layout.addLayout(tab._reason_form)
    layout.addWidget(note)
    return layout


class MaintenanceTab(QWidget):
    """Pestaña para exportar CSV, purgar por retención y ver las métricas de la revisión."""

    # Asignados por las funciones `_build_*` (fuera de la clase, para no superar el límite
    # de líneas por clase de ARQUITECTURA §6).
    _export_combo: QComboBox
    _export_button: QPushButton
    _export_label: QLabel
    _retention_label: QLabel
    _purge_button: QPushButton
    _purge_label: QLabel
    _metrics_button: QPushButton
    _metrics_message: QLabel
    _metrics_form: QFormLayout
    _reason_form: QFormLayout
    _metric_labels: dict[str, QLabel]
    _reason_labels: dict[str, QLabel]

    data_changed = Signal()

    def __init__(self, session: GuiSession) -> None:
        """Construye la pestaña con sus tres secciones.

        Args:
            session: sesión de la GUI de la que se toman el repositorio y los puertos.
        """
        super().__init__()
        self._session = session
        layout = QVBoxLayout(self)
        layout.addLayout(_build_export_row(self))
        layout.addLayout(_build_retention_column(self))
        layout.addLayout(_build_metrics_section(self))

    def export(self) -> None:
        """Exporta los avistamientos del estado elegido y muestra el nombre del archivo."""
        status = _selected_status(self._export_combo)
        use_case = ExportSightings(
            self._session.repository, self._session.export_store, self._session.clock
        )
        try:
            path = use_case.execute(status)
        except (ExportError, RepositoryError) as error:
            QMessageBox.warning(self, DIALOG_TITLE, str(error))
            return
        self._export_label.setText(f"exportado: {path.name}")

    def purge(self) -> None:
        """Pide confirmación y, si se acepta, purga por retención y avisa del resultado."""
        answer = QMessageBox.question(
            self,
            DIALOG_TITLE,
            PURGE_CONFIRM_MESSAGE,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        session = self._session
        use_case = composition.build_purge(
            session.config,
            session.repository,
            session.crop_store,
            session.export_store,
            session.clock,
        )
        try:
            result = use_case.execute()
        except LectorPlacasError as error:
            QMessageBox.warning(self, DIALOG_TITLE, str(error))
            return
        self._purge_label.setText(
            f"recortes={result.crops_deleted} avistamientos={result.sightings_deleted} "
            f"corridas={result.runs_deleted} placas={result.plates_deleted} "
            f"exportaciones={result.exports_deleted}"
        )
        self.data_changed.emit()

    def compute_metrics(self) -> None:
        """Calcula las métricas de la revisión sobre todos los avistamientos y las muestra."""
        records = _collect_all(self._session.repository)
        try:
            metrics = compute_review_metrics(records)
        except EvaluationError as error:
            self._metrics_message.setText(str(error))
            return
        self._metrics_message.setText("")
        self._show_metrics(metrics)

    def set_busy(self, busy: bool) -> None:
        """Deshabilita exportar y purgar mientras hay un procesamiento en curso."""
        self._export_button.setEnabled(not busy)
        self._purge_button.setEnabled(not busy)

    def _show_metrics(self, metrics: ReviewMetrics) -> None:
        """Vuelca `metrics` en las etiquetas fijas y reconstruye las filas de razones."""
        for _text, field, is_rate in _METRIC_ROWS:
            self._metric_labels[field].setText(_format_metric(getattr(metrics, field), is_rate))
        _clear_reason_rows(self._reason_form)
        self._reason_labels = {}
        for reason, count in metrics.reason_counts.items():
            label = QLabel(str(count), self)
            self._reason_form.addRow(reason, label)
            self._reason_labels[reason] = label
