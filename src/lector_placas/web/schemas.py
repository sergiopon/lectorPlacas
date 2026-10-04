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
    duration_ms: int | None


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


class JobRequest(ApiModel):
    """Solicitud de procesamiento."""

    video: str
    profile: str


class JobOut(ApiModel):
    """Estado de un trabajo de procesamiento."""

    job_id: str
    state: Literal["running", "completed", "cancelled", "failed"]
    run_id: int | None
    frames_decoded: int | None
    frames_processed: int | None
    position_ms: int | None
    duration_ms: int | None
    sightings_saved: int | None
    fraction: float | None
    message: str | None


class DecisionIn(ApiModel):
    """Decisión sobre un avistamiento."""

    action: Literal["confirm", "correct", "reject", "illegible"]
    corrected_text: str | None = None


class ExportIn(ApiModel):
    """Solicitud de exportación."""

    status: Literal["unverified", "confirmed", "corrected", "rejected", "illegible"] | None = None


class ExportOut(ApiModel):
    """Resultado de una exportación."""

    file: str


class PurgeOut(ApiModel):
    """Resultado de una purga."""

    crops_deleted: int
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    exports_deleted: int
    training_deleted: int


class MetricsOut(ApiModel):
    """Métricas de la revisión."""

    confirmed_total: int
    confirmed_audited: int
    confirmed_kept: int
    confirmed_corrected: int
    confirmed_rejected: int
    precision_confirmed: float | None
    unverified_total: int
    unverified_confirmed: int
    unverified_corrected: int
    unverified_rejected: int
    unverified_pending: int
    reason_counts: dict[str, int]
    reviewed_readings: int
    cer: float | None
    exact_match_rate: float | None
    confirmed_illegible: int
    unverified_illegible: int
    hidden_total: int
    hidden_legible: int
    hidden_unusable: int
    hidden_pending: int


class SightingCountsOut(ApiModel):
    """Conteos de avistamientos por pestaña."""

    unverified: int
    confirmed: int
    corrected: int
    rejected: int
    illegible: int
    all: int
    hidden: int


class RunMetricsOut(ApiModel):
    """Métricas de una corrida."""

    run_id: int
    legible: int
    illegible: int
    rejected: int
    precision: float | None
    cer: float | None


class SettingsOut(ApiModel):
    """Ajustes de retención."""

    crops_days: int
    records_days: int
    training_days: int
