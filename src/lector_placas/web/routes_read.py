"""Endpoints de lectura de la API web (spec 066)."""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from lector_placas.application.ports import RunRecord, SightingQuery
from lector_placas.domain.entities import PLATE_TEXT_REGEX, ReviewStatus, SightingRecord
from lector_placas.domain.errors import CropNotFoundError, SightingNotFoundError
from lector_placas.web.labels import profile_text
from lector_placas.web.schemas import (
    ProfileOut,
    RunOut,
    RunPage,
    SightingOut,
    SightingPage,
    SummaryOut,
    VideoOut,
)
from lector_placas.web.session import WebSession

router = APIRouter(prefix="/api")

RUNS_PAGE_SIZE: Final[int] = 50
SIGHTINGS_PAGE_SIZE: Final[int] = 48
_STATUSES: Final[frozenset[str]] = frozenset(
    {"unverified", "confirmed", "corrected", "rejected", "illegible"}
)
_HIDDEN_FILTERS: Final[dict[str, Literal["exclude", "only", "include"]]] = {
    "false": "exclude",
    "true": "only",
    "all": "include",
}
_INVALID: Final[str] = "parámetro inválido"


def _session(request: Request) -> WebSession:
    """Devuelve la sesión guardada en el estado de la app."""
    session: WebSession = request.app.state.session
    return session


def _list_videos(session: WebSession) -> list[VideoOut]:
    """Lista los videos de los directorios permitidos."""
    config = session.config
    videos: list[VideoOut] = []
    for directory in config.input.allowed_dirs:
        folder = config.under_root(directory)
        if not folder.exists():
            continue
        for file in sorted(folder.iterdir()):
            if file.is_file() and file.suffix.lower() in config.input.allowed_extensions:
                videos.append(
                    VideoOut(
                        name=file.name,
                        path=file.relative_to(config.root_dir).as_posix(),
                        size_bytes=file.stat().st_size,
                    )
                )
    return videos


def _run_out(session: WebSession, run: RunRecord) -> RunOut:
    """Convierte un `RunRecord` en `RunOut`."""
    profile = session.config.profiles.get(run.profile)
    speed: float | None = None
    if run.duration_ms is not None and run.processing_ms is not None and run.processing_ms > 0:
        speed = run.duration_ms / run.processing_ms
    vehicles: int | None = None
    if (
        run.sightings_confirmed is not None
        and run.sightings_unverified is not None
        and run.tracks_without_reading is not None
    ):
        vehicles = run.sightings_confirmed + run.sightings_unverified + run.tracks_without_reading
    return RunOut(
        id=run.run_id,
        video=f"Video {run.run_id}",
        profile=run.profile,
        mode=None if profile is None else profile.mode,
        started_at=run.started_at,
        duration_ms=run.duration_ms,
        processing_ms=run.processing_ms,
        speed_factor=speed,
        vehicles=vehicles,
        confirmed=run.sightings_confirmed,
        unverified=run.sightings_unverified,
        status=run.status.value,
    )


def _sighting_out(record: SightingRecord, duplicates: int) -> SightingOut:
    """Convierte un `SightingRecord` en `SightingOut`."""
    return SightingOut(
        id=record.sighting_id,
        run_id=record.run_id,
        track_id=record.track_id,
        vehicle_type=record.vehicle_type.value,
        plate_text=record.plate_text,
        ocr_text=record.ocr_text,
        confidence=record.confidence,
        agreement=record.agreement,
        num_readings=record.num_readings,
        status=record.status.value,
        reasons=[reason.value for reason in record.reasons],
        hidden_low_quality=any(r.value.startswith("predicted_") for r in record.reasons),
        duplicates=duplicates,
        duplicate_of=record.duplicate_of,
        first_seen_ms=record.first_seen_ms,
        last_seen_ms=record.last_seen_ms,
        crop_url=None if record.crop_ref is None else f"/api/sightings/{record.sighting_id}/crop",
        created_at=record.created_at,
        reviewed_at=record.reviewed_at,
    )


def _parse_status(status: str | None) -> ReviewStatus | None:
    """Valida el filtro `status`."""
    if status is None:
        return None
    if status not in _STATUSES:
        raise HTTPException(422, _INVALID)
    return ReviewStatus(status)


def _parse_prefix(q: str | None) -> str | None:
    """Valida y normaliza el filtro `q`."""
    if q is None:
        return None
    prefix = q.upper()
    if re.fullmatch(PLATE_TEXT_REGEX.pattern, prefix) is None:
        raise HTTPException(422, _INVALID)
    return prefix


def _parse_hidden(hidden: str) -> Literal["exclude", "only", "include"]:
    """Valida el filtro `hidden`."""
    if hidden not in _HIDDEN_FILTERS:
        raise HTTPException(422, _INVALID)
    return _HIDDEN_FILTERS[hidden]


@router.get("/health")
async def health() -> dict[str, str]:
    """Indica que la API responde."""
    return {"status": "ok"}


@router.get("/videos")
async def videos(request: Request) -> list[VideoOut]:
    """Lista los videos disponibles."""
    return _list_videos(_session(request))


@router.get("/profiles")
async def profiles(request: Request) -> list[ProfileOut]:
    """Lista los perfiles de la configuración."""
    config = _session(request).config
    items: list[ProfileOut] = []
    for name, profile in config.profiles.items():
        label, description = profile_text(name)
        items.append(
            ProfileOut(
                name=name,
                label=label,
                description=description,
                mode=profile.mode,
                default=name == config.default_profile,
            )
        )
    return items


@router.get("/runs")
async def runs(request: Request, page: int = Query(1, ge=1)) -> RunPage:
    """Lista las corridas, paginadas."""
    session = _session(request)
    records = session.browser.list_runs(RUNS_PAGE_SIZE, (page - 1) * RUNS_PAGE_SIZE)
    return RunPage(
        items=[_run_out(session, run) for run in records], page=page, page_size=RUNS_PAGE_SIZE
    )


def _sighting_query(
    status: str | None = None,
    q: str | None = None,
    run: int | None = Query(None, ge=1),
    duplicates: bool = False,
    hidden: str = "false",
) -> SightingQuery:
    """Construye el `SightingQuery` desde los parámetros de la URL."""
    return SightingQuery(
        status=_parse_status(status),
        plate_prefix=_parse_prefix(q),
        run_id=run,
        include_duplicates=duplicates,
        low_quality=_parse_hidden(hidden),
    )


@router.get("/sightings")
async def sightings(
    request: Request,
    query: Annotated[SightingQuery, Depends(_sighting_query)],
    page: int = Query(1, ge=1),
) -> SightingPage:
    """Busca avistamientos, paginados."""
    browser = _session(request).browser
    items = browser.search_sightings(query, SIGHTINGS_PAGE_SIZE, (page - 1) * SIGHTINGS_PAGE_SIZE)
    dups = browser.count_duplicates([r.sighting_id for r in items])
    return SightingPage(
        items=[_sighting_out(r, dups.get(r.sighting_id, 0)) for r in items],
        total=browser.count_sightings(query),
        page=page,
        page_size=SIGHTINGS_PAGE_SIZE,
    )


@router.get("/sightings/{sighting_id}")
async def sighting_detail(request: Request, sighting_id: int) -> SightingOut:
    """Devuelve un avistamiento."""
    session = _session(request)
    try:
        record = session.repository.get_sighting(sighting_id)
    except SightingNotFoundError as error:
        raise HTTPException(404, "avistamiento no encontrado") from error
    duplicates = session.browser.count_duplicates([sighting_id])
    return _sighting_out(record, duplicates.get(sighting_id, 0))


@router.get("/sightings/{sighting_id}/crop")
async def sighting_crop(request: Request, sighting_id: int) -> Response:
    """Devuelve el recorte del avistamiento como PNG, sin escribir a disco."""
    session = _session(request)
    try:
        record = session.repository.get_sighting(sighting_id)
    except SightingNotFoundError as error:
        raise HTTPException(404, "avistamiento no encontrado") from error
    if record.crop_ref is None:
        raise HTTPException(404, "recorte no disponible")
    try:
        image = session.crop_store.load(record.crop_ref)
    except CropNotFoundError as error:
        raise HTTPException(404, "recorte no disponible") from error
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise HTTPException(500, "no se pudo codificar el recorte")
    return Response(content=encoded.tobytes(), media_type="image/png")


@router.get("/summary")
async def summary(request: Request) -> SummaryOut:
    """Cuenta los pendientes visibles y los ocultos por baja calidad."""
    count = _session(request).browser.count_sightings
    return SummaryOut(
        pending=count(SightingQuery(status=ReviewStatus.UNVERIFIED, low_quality="exclude")),
        hidden=count(SightingQuery(status=ReviewStatus.UNVERIFIED, low_quality="only")),
    )
