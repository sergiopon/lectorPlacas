"""Endpoints de acciones de la API web (spec 067)."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from lector_placas.application.export_sightings import ExportSightings
from lector_placas.application.ports import ReviewAction, ReviewDecision
from lector_placas.application.review_sightings import DecideSighting
from lector_placas.cli import composition
from lector_placas.domain.entities import ReviewStatus
from lector_placas.domain.errors import (
    EvaluationError,
    ExportError,
    InputValidationError,
    InvalidEntityError,
    ReviewError,
    SightingNotFoundError,
    UnsafePathError,
)
from lector_placas.evaluation.review_metrics import compute_review_metrics
from lector_placas.web.jobs import JobBusyError, JobManager, JobNotFoundError, JobSnapshot
from lector_placas.web.routes_read import _session, _sighting_out
from lector_placas.web.schemas import (
    DecisionIn,
    ExportIn,
    ExportOut,
    JobOut,
    JobRequest,
    MetricsOut,
    PurgeOut,
    SightingOut,
)

router = APIRouter(prefix="/api")

METRICS_PAGE_SIZE: Final[int] = 500
SSE_INTERVAL_S: Final[float] = 0.25
_NOT_FOUND: Final[str] = "trabajo no encontrado"
_ACTIONS: Final[dict[str, ReviewAction]] = {
    "confirm": ReviewAction.CONFIRM,
    "correct": ReviewAction.CORRECT,
    "reject": ReviewAction.REJECT,
    "illegible": ReviewAction.ILLEGIBLE,
}


def _jobs(request: Request) -> JobManager:
    """Devuelve el gestor de trabajos guardado en el estado de la app."""
    jobs: JobManager = request.app.state.jobs
    return jobs


def _job_out(snap: JobSnapshot) -> JobOut:
    """Convierte un `JobSnapshot` en `JobOut`."""
    progress = snap.progress
    return JobOut(
        job_id=snap.job_id,
        state=snap.state,
        run_id=snap.run_id,
        frames_decoded=None if progress is None else progress.frames_decoded,
        frames_processed=None if progress is None else progress.frames_processed,
        position_ms=None if progress is None else progress.position_ms,
        duration_ms=None if progress is None else progress.duration_ms,
        sightings_saved=None if progress is None else progress.sightings_saved,
        fraction=None if progress is None else progress.fraction,
        message=snap.message,
    )


@router.post("/jobs", status_code=202)
async def start_job(request: Request, body: JobRequest) -> JobOut:
    """Inicia un procesamiento."""
    config = _session(request).config
    if body.profile not in config.profiles:
        raise HTTPException(422, "perfil desconocido")
    try:
        video = composition.validated_video(config, config.root_dir / body.video)
    except (InputValidationError, UnsafePathError) as error:
        raise HTTPException(422, "video no válido") from error
    jobs = _jobs(request)
    try:
        job_id = jobs.start(video, body.profile)
    except JobBusyError as error:
        raise HTTPException(409, "ya hay un procesamiento en curso") from error
    return _job_out(jobs.snapshot(job_id))


@router.get("/jobs/{job_id}")
async def job_detail(request: Request, job_id: str) -> JobOut:
    """Devuelve el estado de un trabajo."""
    try:
        return _job_out(_jobs(request).snapshot(job_id))
    except JobNotFoundError as error:
        raise HTTPException(404, _NOT_FOUND) from error


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_job(request: Request, job_id: str) -> JobOut:
    """Pide cancelar un trabajo."""
    try:
        return _job_out(_jobs(request).cancel(job_id))
    except JobNotFoundError as error:
        raise HTTPException(404, _NOT_FOUND) from error


async def _events(jobs: JobManager, job_id: str) -> AsyncIterator[str]:
    """Genera los eventos SSE del trabajo hasta que termina."""
    while True:
        snap = jobs.snapshot(job_id)
        data = _job_out(snap).model_dump_json(by_alias=True)
        if snap.state == "running":
            yield f"event: progress\ndata: {data}\n\n"
            await asyncio.sleep(SSE_INTERVAL_S)
        else:
            yield f"event: done\ndata: {data}\n\n"
            return


@router.get("/jobs/{job_id}/events")
async def job_events(request: Request, job_id: str) -> StreamingResponse:
    """Emite el avance de un trabajo por Server-Sent Events."""
    jobs = _jobs(request)
    try:
        jobs.snapshot(job_id)
    except JobNotFoundError as error:
        raise HTTPException(404, _NOT_FOUND) from error
    return StreamingResponse(_events(jobs, job_id), media_type="text/event-stream")


@router.post("/sightings/{sighting_id}/decision")
async def decide(request: Request, sighting_id: int, body: DecisionIn) -> SightingOut:
    """Aplica una decisión a un avistamiento."""
    session = _session(request)
    text = None if body.corrected_text is None else body.corrected_text.upper()
    try:
        decision = ReviewDecision(_ACTIONS[body.action], text)
        record = DecideSighting(session.repository, session.clock).execute(sighting_id, decision)
    except (InvalidEntityError, ReviewError) as error:
        raise HTTPException(422, "decisión inválida") from error
    except SightingNotFoundError as error:
        raise HTTPException(404, "avistamiento no encontrado") from error
    duplicates = session.browser.count_duplicates([sighting_id])
    return _sighting_out(record, duplicates.get(sighting_id, 0))


@router.post("/export")
async def export(request: Request, body: ExportIn) -> ExportOut:
    """Exporta los avistamientos a CSV."""
    session = _session(request)
    status = None if body.status is None else ReviewStatus(body.status)
    try:
        path = ExportSightings(session.repository, session.export_store, session.clock).execute(
            status
        )
    except ExportError as error:
        raise HTTPException(500, "no se pudo exportar") from error
    return ExportOut(file=path.name)


@router.post("/purge")
async def purge(request: Request) -> PurgeOut:
    """Purga los datos vencidos según la retención."""
    session = _session(request)
    result = composition.build_purge(
        session.config, session.repository, session.crop_store, session.export_store, session.clock
    ).execute()
    return PurgeOut(
        crops_deleted=result.crops_deleted,
        sightings_deleted=result.sightings_deleted,
        runs_deleted=result.runs_deleted,
        plates_deleted=result.plates_deleted,
        exports_deleted=result.exports_deleted,
        training_deleted=result.training_deleted,
    )


@router.get("/metrics")
async def metrics(request: Request) -> MetricsOut:
    """Calcula las métricas de la revisión."""
    repository = _session(request).repository
    records = []
    offset = 0
    while True:
        page = repository.list_sightings(None, METRICS_PAGE_SIZE, offset)
        records.extend(page)
        if len(page) < METRICS_PAGE_SIZE:
            break
        offset += METRICS_PAGE_SIZE
    try:
        result = compute_review_metrics(records)
    except EvaluationError as error:
        raise HTTPException(404, "no hay avistamientos para evaluar") from error
    return MetricsOut(**dataclasses.asdict(result))
