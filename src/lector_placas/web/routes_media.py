"""Endpoints de video, fotograma, conteos, métricas por corrida y ajustes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Final

import cv2
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from lector_placas.application.ports import SightingQuery
from lector_placas.domain.entities import ReviewStatus, SightingRecord
from lector_placas.domain.errors import SightingNotFoundError, VideoSourceError
from lector_placas.evaluation.review_metrics import compute_review_metrics
from lector_placas.web.media import VIDEO_MEDIA_TYPES, MediaServices
from lector_placas.web.routes_read import _parse_prefix, _session
from lector_placas.web.schemas import RunMetricsOut, SettingsOut, SightingCountsOut
from lector_placas.web.session import WebSession

router = APIRouter(prefix="/api")

_METRICS_PAGE_SIZE: Final[int] = 500
_NO_VIDEO: Final[str] = "video no disponible"
_LEGIBLE: Final[frozenset[ReviewStatus]] = frozenset(
    {ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED}
)


def _media(request: Request) -> MediaServices:
    """Devuelve los servicios de medios guardados en el estado de la app."""
    media: MediaServices = request.app.state.media
    return media


async def _locate_video(request: Request, run_id: int) -> Path:
    """Localiza el video de la corrida o responde 404."""
    session = _session(request)
    sha = session.repository.run_video_hashes().get(run_id)
    if sha is None:
        raise HTTPException(404, _NO_VIDEO)
    path = await run_in_threadpool(_media(request).locator.find, sha)
    if path is None:
        raise HTTPException(404, _NO_VIDEO)
    return path


def _get_record(session: WebSession, sighting_id: int) -> SightingRecord:
    """Lee el avistamiento o responde 404."""
    try:
        return session.repository.get_sighting(sighting_id)
    except SightingNotFoundError as error:
        raise HTTPException(404, "avistamiento no encontrado") from error


def _all_records(session: WebSession) -> list[SightingRecord]:
    """Lee todos los avistamientos paginando."""
    records: list[SightingRecord] = []
    offset = 0
    while True:
        page = session.repository.list_sightings(None, _METRICS_PAGE_SIZE, offset)
        records.extend(page)
        if len(page) < _METRICS_PAGE_SIZE:
            return records
        offset += _METRICS_PAGE_SIZE


def _run_metrics(run_id: int, group: list[SightingRecord]) -> RunMetricsOut:
    """Calcula las métricas de una corrida."""
    result = compute_review_metrics(group)
    return RunMetricsOut(
        run_id=run_id,
        legible=sum(1 for r in group if r.status in _LEGIBLE),
        illegible=sum(1 for r in group if r.status is ReviewStatus.ILLEGIBLE),
        rejected=sum(1 for r in group if r.status is ReviewStatus.REJECTED),
        precision=result.precision_confirmed,
        cer=result.cer,
    )


@router.get("/runs/{run_id}/video")
async def run_video(request: Request, run_id: int) -> Response:
    """Sirve el video original de la corrida, con soporte de `Range`."""
    path = await _locate_video(request, run_id)
    media_type = VIDEO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.get("/sightings/{sighting_id}/frame")
async def sighting_frame(request: Request, sighting_id: int) -> Response:
    """Devuelve el fotograma completo del avistamiento como PNG, sin escribir a disco."""
    record = _get_record(_session(request), sighting_id)
    path = await _locate_video(request, record.run_id)
    timestamp = (record.first_seen_ms + record.last_seen_ms) // 2
    try:
        image = await run_in_threadpool(_media(request).grabber.grab, path, timestamp)
    except VideoSourceError as error:
        raise HTTPException(404, "fotograma no disponible") from error
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise HTTPException(500, "no se pudo codificar el fotograma")
    return Response(
        content=encoded.tobytes(),
        media_type="image/png",
        headers={"X-Frame-Timestamp-Ms": str(timestamp)},
    )


@router.get("/sighting-counts")
async def sighting_counts(
    request: Request,
    q: str | None = None,
    run: int | None = Query(None, ge=1),
    duplicates: bool = False,
) -> SightingCountsOut:
    """Cuenta los avistamientos por estado, el total visible y los ocultos."""
    count = _session(request).browser.count_sightings
    base = SightingQuery(plate_prefix=_parse_prefix(q), run_id=run, include_duplicates=duplicates)

    def by_status(status: ReviewStatus) -> int:
        return count(replace(base, status=status, low_quality="exclude"))

    return SightingCountsOut(
        unverified=by_status(ReviewStatus.UNVERIFIED),
        confirmed=by_status(ReviewStatus.CONFIRMED),
        corrected=by_status(ReviewStatus.CORRECTED),
        rejected=by_status(ReviewStatus.REJECTED),
        illegible=by_status(ReviewStatus.ILLEGIBLE),
        all=count(replace(base, low_quality="exclude")),
        hidden=count(replace(base, low_quality="only")),
    )


@router.get("/metrics/runs")
async def metrics_by_run(request: Request) -> list[RunMetricsOut]:
    """Calcula las métricas de revisión de cada corrida."""
    groups: dict[int, list[SightingRecord]] = {}
    for record in _all_records(_session(request)):
        groups.setdefault(record.run_id, []).append(record)
    return [_run_metrics(run_id, groups[run_id]) for run_id in sorted(groups)]


@router.get("/settings")
async def settings(request: Request) -> SettingsOut:
    """Devuelve los ajustes de retención."""
    retention = _session(request).config.retention
    return SettingsOut(
        crops_days=retention.crops_days,
        records_days=retention.records_days,
        training_days=retention.training_days,
    )
