from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtWidgets import QMessageBox

from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ExportError
from lector_placas.evaluation.review_metrics import EMPTY_MESSAGE, compute_review_metrics
from lector_placas.gui.labels import percent
from lector_placas.gui.maintenance_tab import METRICS_PAGE_SIZE, MaintenanceTab
from lector_placas.gui.session import GuiSession
from lector_placas.infrastructure.config import AppConfig
from tests.fixtures.fakes import (
    FakeClock,
    FakeKeyProvider,
    InMemoryCropStore,
    InMemoryExportStore,
    InMemoryPlateRepository,
)

CREATED_AT = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


def _session(config: AppConfig, export_store=None) -> GuiSession:
    repository = InMemoryPlateRepository()
    return GuiSession(
        config,
        FakeKeyProvider(),
        FakeClock(),
        repository,
        repository,
        InMemoryCropStore(),
        export_store if export_store is not None else InMemoryExportStore(),
    )


def _add_sighting(
    session: GuiSession, plate_text: str, status: ReviewStatus, run_id: int = 1
) -> int:
    reasons = () if status is ReviewStatus.CONFIRMED else (UnverifiedReason.INSUFFICIENT_READINGS,)
    plate = ConsolidatedPlate(
        text=plate_text,
        confidence=0.5,
        agreement=0.5,
        num_readings=1,
        status=status,
        reasons=reasons,
        format_ids=(),
    )
    sighting = Sighting(
        run_id=run_id,
        track_id=1,
        first_seen_ms=0,
        last_seen_ms=1000,
        vehicle_type=VehicleType.CAR,
        plate=plate,
        crop_ref=None,
        created_at=CREATED_AT,
    )
    return session.repository.save_sighting(sighting)


class _FailingExportStore:
    def write_sightings(self, records, created_at):
        raise ExportError("fallo al escribir el CSV")

    def delete_older_than(self, cutoff):
        return 0


class _FakePurge:
    def __init__(self, result: PurgeResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self) -> PurgeResult:
        self.calls += 1
        return self.result


def test_export_writes_and_shows_file_name(config: AppConfig, qapp) -> None:
    session = _session(config)
    _add_sighting(session, "AAA111", ReviewStatus.CONFIRMED)
    _add_sighting(session, "BBB222", ReviewStatus.UNVERIFIED)
    tab = MaintenanceTab(session)

    tab._export_button.click()
    assert tab._export_label.text() == "exportado: sightings-1.csv"

    tab._export_combo.setCurrentIndex(1 + tuple(ReviewStatus).index(ReviewStatus.CONFIRMED))
    tab._export_button.click()
    assert tab._export_label.text() == "exportado: sightings-2.csv"
    assert len(session.export_store.written[1][0]) == 1


def test_export_error_warns(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config, export_store=_FailingExportStore())
    tab = MaintenanceTab(session)
    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    tab._export_button.click()

    assert len(warnings) == 1
    assert warnings[0][2] == "fallo al escribir el CSV"


def test_retention_label_uses_config(config: AppConfig, qapp) -> None:
    tab = MaintenanceTab(_session(config))
    retention = config.retention
    expected = (
        f"Retención: recortes {retention.crops_days} días · registros {retention.records_days} días"
        f" · entrenamiento {retention.training_days} días"
    )
    assert tab._retention_label.text() == expected


def test_purge_asks_confirmation_and_reports_counts(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    tab = MaintenanceTab(session)
    result = PurgeResult(1, 2, 3, 4, 5)
    fake = _FakePurge(result)
    monkeypatch.setattr(composition, "build_purge", lambda *a, **k: fake)
    questions: list[tuple] = []

    def fake_question(*args):
        questions.append(args)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    tab._purge_button.click()

    assert len(questions) == 1
    assert questions[0][2] == "Se borrarán los datos vencidos según la retención. ¿Continuar?"
    assert fake.calls == 1
    assert tab._purge_label.text() == (
        "recortes=1 avistamientos=2 corridas=3 placas=4 exportaciones=5"
    )


def test_purge_cancelled_does_nothing(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    tab = MaintenanceTab(session)

    def boom(*a, **k):
        raise AssertionError("build_purge no debería llamarse")

    monkeypatch.setattr(composition, "build_purge", boom)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)

    tab._purge_button.click()

    assert tab._purge_label.text() == ""


def test_purge_emits_data_changed(config: AppConfig, monkeypatch, qapp) -> None:
    session = _session(config)
    tab = MaintenanceTab(session)
    fake = _FakePurge(PurgeResult(0, 0, 0, 0, 0))
    monkeypatch.setattr(composition, "build_purge", lambda *a, **k: fake)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    emitted = []
    tab.data_changed.connect(lambda: emitted.append(True))

    tab._purge_button.click()

    assert emitted == [True]


_METRIC_FIELDS = (
    "confirmed_total",
    "confirmed_audited",
    "confirmed_kept",
    "confirmed_corrected",
    "confirmed_rejected",
    "unverified_total",
    "unverified_pending",
    "unverified_confirmed",
    "unverified_corrected",
    "unverified_rejected",
    "reviewed_readings",
)


def _build_metrics_dataset(session: GuiSession, total: int) -> None:
    """Crea `total` avistamientos: confirmados (una cuarta parte auditados como rechazados,
    para dejar CER y coincidencia exacta en `None`) y sin verificar sin auditar."""
    for index in range(total):
        plate_text = f"AAA{index % 10}{index % 10}{index % 10}"
        if index % 2 != 0:
            _add_sighting(session, plate_text, ReviewStatus.UNVERIFIED)
        elif index % 4 == 0:
            sighting_id = _add_sighting(session, plate_text, ReviewStatus.CONFIRMED)
            session.repository.record_review(sighting_id, ReviewStatus.REJECTED, None, CREATED_AT)
        else:
            _add_sighting(session, plate_text, ReviewStatus.CONFIRMED)


def _assert_fixed_metrics(tab: MaintenanceTab, expected) -> None:
    for field in _METRIC_FIELDS:
        assert tab._metric_labels[field].text() == str(getattr(expected, field))


def _assert_reason_rows(tab: MaintenanceTab, expected) -> None:
    assert set(tab._reason_labels) == set(expected.reason_counts)
    for reason, count in expected.reason_counts.items():
        assert tab._reason_labels[reason].text() == str(count)


def test_metrics_paginates_and_displays(config: AppConfig, qapp) -> None:
    session = _session(config)
    total = 2 * METRICS_PAGE_SIZE + 200
    _build_metrics_dataset(session, total)
    all_records = session.repository.list_sightings(None, total, 0)
    assert len(all_records) == total
    expected = compute_review_metrics(all_records)
    assert expected.precision_confirmed is not None
    assert expected.cer is None
    assert expected.exact_match_rate is None
    tab = MaintenanceTab(session)

    tab._metrics_button.click()

    assert tab._metrics_message.text() == ""
    _assert_fixed_metrics(tab, expected)
    _assert_reason_rows(tab, expected)
    assert tab._metric_labels["precision_confirmed"].text() == percent(expected.precision_confirmed)
    assert tab._metric_labels["cer"].text() == "n/d"
    assert tab._metric_labels["exact_match_rate"].text() == "n/d"


def test_metrics_without_sightings_shows_message(config: AppConfig, qapp) -> None:
    tab = MaintenanceTab(_session(config))

    tab._metrics_button.click()

    assert tab._metrics_message.text() == EMPTY_MESSAGE


def test_busy_disables_export_and_purge_only(config: AppConfig, qapp) -> None:
    tab = MaintenanceTab(_session(config))

    tab.set_busy(True)
    assert tab._export_button.isEnabled() is False
    assert tab._purge_button.isEnabled() is False
    assert tab._metrics_button.isEnabled() is True

    tab.set_busy(False)
    assert tab._export_button.isEnabled() is True
    assert tab._purge_button.isEnabled() is True
    assert tab._metrics_button.isEnabled() is True
