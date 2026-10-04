"""Subcomando `evaluate-review` de la CLI `lector` (spec 038)."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import TYPE_CHECKING

from lector_placas.application.ports import Clock, CropStore, ExportStore, PlateRepository
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import commands
from lector_placas.cli.commands import _run_with_repository
from lector_placas.cli.evaluation_commands import PAGE_SIZE, _format_metric, _reports_dir
from lector_placas.domain.entities import SightingRecord
from lector_placas.evaluation.report import write_report
from lector_placas.evaluation.review_metrics import ReviewMetrics, compute_review_metrics

if TYPE_CHECKING:
    from lector_placas.infrastructure.config import AppConfig


def register_review_evaluation(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Registra `evaluate-review` en el parser de la CLI.

    Args:
        subparsers: acción de subparsers de `main.build_parser`.
    """
    parser = subparsers.add_parser("evaluate-review")
    parser.set_defaults(handler=cmd_evaluate_review, network=False, key="load")


def cmd_evaluate_review(args: argparse.Namespace, config: AppConfig) -> int:
    """Calcula las métricas de la revisión sobre toda la base y escribe el reporte."""

    def action(
        repository: PlateRepository,
        crop_store: CropStore,
        export_store: ExportStore,
        clock: Clock,
        purge: PurgeResult,
    ) -> int:
        del crop_store, export_store, purge
        metrics = compute_review_metrics(_all_sightings(repository))
        payload: dict[str, object] = {"kind": "review", **dataclasses.asdict(metrics)}
        report = write_report(_reports_dir(config), payload, clock.now())
        _write_summary(metrics, report.name)
        return 0

    return _run_with_repository(config, commands.require_keys(args), action)


def _all_sightings(repository: PlateRepository) -> list[SightingRecord]:
    """Recupera, paginando, todos los avistamientos de la base."""
    records: list[SightingRecord] = []
    offset = 0
    while True:
        page = repository.list_sightings(None, PAGE_SIZE, offset)
        records.extend(page)
        if len(page) < PAGE_SIZE:
            return records
        offset += PAGE_SIZE


def _write_summary(metrics: ReviewMetrics, report_name: str) -> None:
    """Escribe en stdout las métricas de la revisión y el reporte, sin placas."""
    sys.stdout.write(
        f"confirmed_audited={metrics.confirmed_audited} "
        f"precision_confirmed={_format_metric(metrics.precision_confirmed)} "
        f"unverified_total={metrics.unverified_total} "
        f"unverified_pending={metrics.unverified_pending} "
        f"reviewed_readings={metrics.reviewed_readings} "
        f"cer={_format_metric(metrics.cer)} "
        f"exact_match_rate={_format_metric(metrics.exact_match_rate)}\n"
    )
    sys.stdout.write(
        f"ocultas={metrics.hidden_total} "
        f"ocultas_legibles={metrics.hidden_legible} "
        f"ocultas_inservibles={metrics.hidden_unusable} "
        f"ocultas_pendientes={metrics.hidden_pending}\n"
    )
    sys.stdout.write(f"reporte={report_name}\n")
