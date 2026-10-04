"""Modelos de la API web (JSON en camelCase)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base de los modelos de la API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class VideoOut(ApiModel):
    """Video disponible para procesar."""

    name: str
    path: str
    size_bytes: int


class ProfileOut(ApiModel):
    """Perfil de procesamiento."""

    name: str
    label: str
    description: str
    mode: Literal["estatico", "movil"]
    default: bool


class RunOut(ApiModel):
    """Corrida registrada."""

    id: int
    video: str
    profile: str
    mode: Literal["estatico", "movil"] | None
    started_at: datetime
    duration_ms: int | None
    processing_ms: int | None
    speed_factor: float | None
    vehicles: int | None
    confirmed: int | None
    unverified: int | None
    status: Literal["running", "completed", "failed"]


class RunPage(ApiModel):
    """Página de corridas."""

    items: list[RunOut]
    page: int
    page_size: int


class SightingOut(ApiModel):
    """Avistamiento."""

    id: int
    run_id: int
    track_id: int
    vehicle_type: str
    plate_text: str
    ocr_text: str
    confidence: float
    agreement: float
    num_readings: int
    status: str
    reasons: list[str]
    hidden_low_quality: bool
    duplicates: int
    duplicate_of: int | None
    first_seen_ms: int
    last_seen_ms: int
    crop_url: str | None
    created_at: datetime
    reviewed_at: datetime | None


class SightingPage(ApiModel):
    """Página de avistamientos."""

    items: list[SightingOut]
    total: int
    page: int
    page_size: int


class SummaryOut(ApiModel):
    """Resumen de pendientes y ocultos."""

    pending: int
    hidden: int


class ErrorOut(ApiModel):
    """Error de la API."""

    detail: str
