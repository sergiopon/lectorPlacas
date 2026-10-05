"""Puertos (Protocols) y DTOs de la capa de aplicación."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

import numpy as np
import numpy.typing as npt

from lector_placas.domain.entities import (
    PLATE_TEXT_REGEX,
    ConsolidatedPlate,
    OcrResult,
    PlateDetection,
    PlateReading,
    ReviewStatus,
    Sighting,
    SightingRecord,
    TrackedVehicle,
    UnverifiedReason,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import InvalidEntityError

# `ImageBGR` es (alto, ancho, 3) en BGR. La forma la fija docs/02-contratos.md §4, que usa
# `TypeAlias`; por eso UP040 (que preferiría el `type` de PEP 695) queda silenciada a propósito.
ImageBGR: TypeAlias = npt.NDArray[np.uint8]  # noqa: UP040
LowQualityFilter: TypeAlias = Literal["include", "exclude", "only"]  # noqa: UP040
SHA256_REGEX = re.compile(r"^[0-9a-f]{64}$")
ROTATIONS_DEG = (0, 90, 180, 270)
IMAGE_NDIM = 3
IMAGE_CHANNELS = 3


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """Frame decodificado con su índice, marca de tiempo e imagen BGR upright."""

    index: int
    timestamp_ms: int
    image: ImageBGR

    def __post_init__(self) -> None:
        """Valida el índice, la marca de tiempo y la imagen BGR."""
        if self.index < 0:
            raise InvalidEntityError(f"index debe ser >= 0: {self.index}")
        if self.timestamp_ms < 0:
            raise InvalidEntityError(f"timestamp_ms debe ser >= 0: {self.timestamp_ms}")
        if (
            self.image.ndim != IMAGE_NDIM
            or self.image.shape[2] != IMAGE_CHANNELS
            or self.image.dtype != np.uint8
            or self.image.shape[0] == 0
            or self.image.shape[1] == 0
        ):
            raise InvalidEntityError(
                f"imagen inválida: shape={self.image.shape}, dtype={self.image.dtype}"
            )

    @property
    def width(self) -> int:
        """Ancho de la imagen en píxeles."""
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        """Alto de la imagen en píxeles."""
        return int(self.image.shape[0])


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Metadatos del video, ya aplicada la rotación."""

    width: int
    height: int
    rotation_deg: int
    duration_ms: int | None
    average_fps: float | None
    codec: str

    def __post_init__(self) -> None:
        """Valida dimensiones, rotación, duración, fps y códec."""
        if self.width <= 0 or self.height <= 0:
            raise InvalidEntityError(f"dimensiones inválidas: {self.width}x{self.height}")
        if self.rotation_deg not in ROTATIONS_DEG:
            raise InvalidEntityError(f"rotation_deg inválido: {self.rotation_deg}")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise InvalidEntityError(f"duration_ms debe ser >= 0: {self.duration_ms}")
        if self.average_fps is not None and (
            not np.isfinite(self.average_fps) or self.average_fps <= 0.0
        ):
            raise InvalidEntityError(f"average_fps inválido: {self.average_fps}")
        if not self.codec.strip():
            raise InvalidEntityError("codec no puede estar vacío")


@dataclass(frozen=True, slots=True)
class RunStart:
    """Datos de apertura de una corrida de procesamiento."""

    video_sha256: str
    profile: str
    video: VideoInfo
    started_at: datetime

    def __post_init__(self) -> None:
        """Valida el hash del video, el perfil y la fecha UTC de inicio."""
        if SHA256_REGEX.fullmatch(self.video_sha256) is None:
            raise InvalidEntityError("video_sha256 debe ser un SHA-256 en hexadecimal minúscula")
        if not self.profile.strip():
            raise InvalidEntityError("profile no puede estar vacío")
        _require_utc(self.started_at, "started_at")


@dataclass(frozen=True, slots=True)
class RunStats:
    """Estadísticas agregadas de una corrida de procesamiento."""

    frames_decoded: int
    frames_processed: int
    tracks_total: int
    sightings_confirmed: int
    sightings_unverified: int
    tracks_without_reading: int
    processing_ms: int
    video_duration_ms: int | None

    def __post_init__(self) -> None:
        """Valida que los conteos y tiempos sean no negativos."""
        if any(value < 0 for value in _counters(self)):
            raise InvalidEntityError("los conteos de RunStats deben ser >= 0")
        if self.video_duration_ms is not None and self.video_duration_ms < 0:
            raise InvalidEntityError(f"video_duration_ms debe ser >= 0: {self.video_duration_ms}")

    @property
    def speed_factor(self) -> float | None:
        """Relación entre la duración del video y el tiempo de procesamiento."""
        if self.video_duration_ms is None or self.processing_ms == 0:
            return None
        return self.video_duration_ms / self.processing_ms


@dataclass(frozen=True, slots=True)
class RecordPurge:
    """Conteos y recortes afectados por una purga de registros."""

    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    crop_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Valida que los conteos sean no negativos."""
        if self.sightings_deleted < 0 or self.runs_deleted < 0 or self.plates_deleted < 0:
            raise InvalidEntityError("los conteos de RecordPurge deben ser >= 0")


class AuditEvent(StrEnum):
    """Tipo de evento del registro de auditoría."""

    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    REVIEW = "review"
    PURGE = "purge"
    EXPORT = "export"


class ReviewAction(StrEnum):
    """Acción que puede tomar el operador sobre un avistamiento."""

    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    SKIP = "skip"
    QUIT = "quit"
    ILLEGIBLE = "illegible"


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    """Decisión tomada por el operador sobre un avistamiento."""

    action: ReviewAction
    corrected_text: str | None = None

    def __post_init__(self) -> None:
        """Valida la coherencia entre la acción y el texto corregido."""
        if self.action is ReviewAction.CORRECT:
            if self.corrected_text is None:
                raise InvalidEntityError("la acción CORRECT exige corrected_text")
            if PLATE_TEXT_REGEX.fullmatch(self.corrected_text) is None:
                raise InvalidEntityError("corrected_text no cumple el formato de placa")
        elif self.corrected_text is not None:
            raise InvalidEntityError("corrected_text solo se admite con la acción CORRECT")


class VideoSource(Protocol):
    """Fuente de video abierta que entrega frames BGR upright."""

    def info(self) -> VideoInfo:
        """Metadatos del video abierto.

        Precondiciones:
            La fuente está abierta.

        Postcondiciones:
            `VideoInfo` coherente con el stream de video.

        Raises:
            VideoSourceError: si el contenedor no expone información válida.
        """
        ...

    def frames(self) -> Iterator[Frame]:
        """Itera los frames decodificados en orden.

        Precondiciones:
            Fuente abierta; se llama una sola vez.

        Postcondiciones:
            `Frame` en orden de decodificación, `timestamp_ms` no decreciente, imagen upright BGR.

        Raises:
            VideoSourceError: ante error de decodificación.
        """
        ...

    def close(self) -> None:
        """Libera el contenedor de video.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Idempotente; libera el contenedor.
        """
        ...


class VideoSourceFactory(Protocol):
    """Abre archivos de video como fuentes de frames."""

    def open(self, path: Path) -> VideoSource:
        """Abre el archivo de video indicado.

        Precondiciones:
            `path` ya validado.

        Postcondiciones:
            Fuente abierta; `info()` disponible.

        Raises:
            VideoSourceError: si no decodifica o no tiene stream de video.
        """
        ...


class FrameGrabber(Protocol):
    """Obtiene el fotograma completo de un video en un instante dado."""

    def grab(self, path: Path, timestamp_ms: int) -> ImageBGR:
        """Decodifica el fotograma de `path` en `timestamp_ms`.

        Precondiciones:
            `path` es un video ya localizado por `VideoLocator`; `timestamp_ms >= 0`.

        Postcondiciones:
            Imagen BGR upright (rotación aplicada) del primer frame cuyo timestamp (relativo al
            PTS del primer frame) es `>= timestamp_ms`; si el video termina antes, el último
            frame decodificado.

        Raises:
            VideoSourceError: si no se puede abrir o decodificar el video.
        """
        ...


class FrameSampler(Protocol):
    """Decide qué frames se procesan según su marca de tiempo."""

    def should_process(self, timestamp_ms: int) -> bool:
        """Indica si el frame con esa marca de tiempo debe procesarse.

        Precondiciones:
            `timestamp_ms >= 0`.

        Postcondiciones:
            `True` para el primer frame; luego según ADR-006.
        """
        ...

    def reset(self) -> None:
        """Reinicia el estado del muestreador.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Estado vacío; el próximo frame vuelve a procesarse.
        """
        ...


class VehicleDetector(Protocol):
    """Detecta vehículos en un frame."""

    def detect(self, image: ImageBGR) -> list[VehicleDetection]:
        """Detecta vehículos en la imagen BGR.

        Precondiciones:
            Imagen BGR válida.

        Postcondiciones:
            Cajas dentro de la imagen, `confidence >= umbral` configurado, solo 4 tipos.

        Raises:
            InferenceError: si falla la inferencia.
        """
        ...


class PlateDetector(Protocol):
    """Detecta placas dentro de un recorte de vehículo."""

    def detect(self, image: ImageBGR) -> list[PlateDetection]:
        """Detecta placas en la imagen BGR recibida.

        Precondiciones:
            Imagen BGR con lados >= 16 px.

        Postcondiciones:
            Cajas en coordenadas de esa imagen, ordenadas por confianza descendente.

        Raises:
            InferenceError: si falla la inferencia.
        """
        ...


class Tracker(Protocol):
    """Asigna identificadores persistentes a los vehículos detectados."""

    def update(
        self, detections: Sequence[VehicleDetection], image: ImageBGR, timestamp_ms: int
    ) -> list[TrackedVehicle]:
        """Actualiza el seguimiento con las detecciones del frame.

        Precondiciones:
            `timestamp_ms` no decreciente entre llamadas.

        Postcondiciones:
            Solo `track_id >= 0`; cada salida corresponde a una detección de entrada.

        Raises:
            TrackingError: si falla el seguimiento.
        """
        ...

    def reset(self) -> None:
        """Reinicia el estado del tracker.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Estado vacío; los IDs reinician en 0.
        """
        ...


class PlateReader(Protocol):
    """Lee el texto de las placas recortadas."""

    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]:
        """Lee en lote las imágenes de placa recibidas.

        Precondiciones:
            Lista (posiblemente vacía) de imágenes BGR.

        Postcondiciones:
            Misma longitud y orden que la entrada.

        Raises:
            InferenceError: si falla la inferencia.
        """
        ...


class ImageQualityScorer(Protocol):
    """Puntúa la nitidez de un recorte de placa."""

    def sharpness(self, image: ImageBGR) -> float:
        """Calcula la nitidez de la imagen BGR.

        Precondiciones:
            Imagen BGR no vacía.

        Postcondiciones:
            Valor finito >= 0.
        """
        ...


class PlateConsolidator(Protocol):
    """Combina las lecturas de un track en una placa consolidada."""

    def consolidate(
        self, readings: Sequence[PlateReading], vehicle_type: VehicleType
    ) -> ConsolidatedPlate:
        """Consolida las lecturas de un track.

        Precondiciones:
            >= 1 lectura, todas del mismo `track_id`.

        Postcondiciones:
            `ConsolidatedPlate` válido.

        Raises:
            ConsolidationError: si las lecturas son incoherentes.
        """
        ...


class PlateRepository(Protocol):
    """Persiste corridas, avistamientos y eventos de auditoría."""

    def start_run(self, run: RunStart) -> int:
        """Registra el inicio de una corrida.

        Precondiciones:
            BD abierta.

        Postcondiciones:
            `run_id >= 1`; corrida en estado `running`.

        Raises:
            RepositoryError: si falla la escritura.
        """
        ...

    def finish_run(
        self, run_id: int, stats: RunStats, finished_at: datetime, succeeded: bool
    ) -> None:
        """Cierra una corrida con sus estadísticas y resultado.

        Precondiciones:
            `run_id` existe.

        Postcondiciones:
            Corrida marcada como terminada con sus estadísticas y resultado.

        Raises:
            RepositoryError: si falla la escritura.
        """
        ...

    def save_sighting(self, sighting: Sighting) -> int:
        """Guarda un avistamiento.

        Precondiciones:
            `sighting.run_id` existe.

        Postcondiciones:
            Fila insertada; si CONFIRMED, placa enlazada en `plates`.

        Raises:
            RepositoryError: si falla la escritura.
        """
        ...

    def list_sightings(
        self, status: ReviewStatus | None, limit: int, offset: int
    ) -> list[SightingRecord]:
        """Lista avistamientos paginados, opcionalmente filtrados por estado.

        Precondiciones:
            `limit >= 0` y `offset >= 0`.

        Postcondiciones:
            Registros ordenados por `sighting_id`, con el filtro y la paginación aplicados.

        Raises:
            RepositoryError: si falla la lectura.
        """
        ...

    def get_sighting(self, sighting_id: int) -> SightingRecord:
        """Recupera un avistamiento por su identificador.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Registro con ese `sighting_id`.

        Raises:
            SightingNotFoundError: si el avistamiento no existe.
        """
        ...

    def record_review(
        self,
        sighting_id: int,
        status: ReviewStatus,
        corrected_text: str | None,
        reviewed_at: datetime,
    ) -> None:
        """Registra la decisión de revisión de un avistamiento.

        Precondiciones:
            `status` ∈ {CONFIRMED, CORRECTED, REJECTED, ILLEGIBLE}; `corrected_text` solo con
            CORRECTED.

        Postcondiciones:
            Estado, `plate_text`, `plate_id` y `reviewed_at` actualizados.

        Raises:
            SightingNotFoundError: si el avistamiento no existe.
            RepositoryError: si falla la escritura.
        """
        ...

    def expire_crop_refs(self, cutoff: datetime) -> list[str]:
        """Desvincula los recortes de avistamientos anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            `crop_ref` puesto a `None` en los avistamientos anteriores a `cutoff`;
            devuelve las referencias afectadas.

        Raises:
            RepositoryError: si falla la escritura.
        """
        ...

    def delete_records_before(self, cutoff: datetime) -> RecordPurge:
        """Borra los registros anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            Avistamientos, corridas y placas anteriores a `cutoff` borrados; devuelve los conteos.

        Raises:
            RepositoryError: si falla el borrado.
        """
        ...

    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None:
        """Añade un evento al registro de auditoría.

        Precondiciones:
            `detail` sin texto de placa en claro.

        Postcondiciones:
            Evento persistido con su fecha y detalle.

        Raises:
            RepositoryError: si falla la escritura.
        """
        ...

    def run_video_hashes(self) -> dict[int, str]:
        """Devuelve el hash del video de cada corrida registrada.

        Precondiciones:
            BD abierta.

        Postcondiciones:
            `run_id` → `video_sha256` de todas las corridas existentes.

        Raises:
            RepositoryError: si falla la lectura.
        """
        ...

    def run_frame_sizes(self) -> dict[int, tuple[int, int]]:
        """Devuelve el tamaño del frame de cada corrida registrada.

        Precondiciones:
            BD abierta.

        Postcondiciones:
            `run_id` → `(width, height)` tal como se guardaron en `runs`.

        Raises:
            RepositoryError: si falla la lectura.
        """
        ...

    def mark_duplicates(self, pairs: Sequence[tuple[int, int]]) -> None:
        """Marca avistamientos como duplicados de otro de la misma corrida.

        Precondiciones:
            BD abierta; cada par es `(sighting_id del duplicado, sighting_id del conservado)`.

        Postcondiciones:
            `duplicate_of` del duplicado queda igual al conservado, en una sola transacción.

        Raises:
            RepositoryError: si falla la escritura (no queda ningún cambio).
        """
        ...

    def close(self) -> None:
        """Cierra la base de datos.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            BD cerrada; idempotente.
        """
        ...


class CropStore(Protocol):
    """Almacena los recortes de placa cifrados."""

    def save(self, image: ImageBGR) -> str:
        """Guarda un recorte cifrado.

        Precondiciones:
            Imagen BGR no vacía.

        Postcondiciones:
            `crop_ref` de 32 hex; archivo cifrado 0600.

        Raises:
            CropStoreError: si falla la escritura.
            EncryptionError: si falla el cifrado.
        """
        ...

    def load(self, crop_ref: str) -> ImageBGR:
        """Recupera un recorte cifrado.

        Precondiciones:
            `crop_ref` válido.

        Postcondiciones:
            Imagen idéntica píxel a píxel a la guardada.

        Raises:
            CropNotFoundError: si el recorte no existe.
            EncryptionError: si falla el descifrado.
        """
        ...

    def delete(self, crop_ref: str) -> None:
        """Borra un recorte.

        Precondiciones:
            `crop_ref` válido.

        Postcondiciones:
            Archivo inexistente; idempotente.

        Raises:
            CropStoreError: si falla el borrado.
        """
        ...

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra los recortes anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            Archivos de recorte con fecha de modificación < `cutoff` borrados (huérfanos
            incluidos); devuelve cuántos.

        Raises:
            CropStoreError: si falla el borrado.
        """
        ...


class ExportStore(Protocol):
    """Escribe exportaciones de avistamientos y limpia las vencidas."""

    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path:
        """Escribe una exportación con los avistamientos indicados.

        Precondiciones:
            `created_at` en UTC.

        Postcondiciones:
            CSV nuevo 0600 en el directorio de exportaciones.

        Raises:
            ExportError: si falla la escritura.
        """
        ...

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra las exportaciones anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            Exportaciones anteriores a `cutoff` borradas; devuelve cuántas.

        Raises:
            ExportError: si falla el borrado.
        """
        ...


class TrainingExportStore(Protocol):
    """Escribe muestras de entrenamiento del OCR y limpia las vencidas."""

    def write_samples(self, samples: Sequence[tuple[str, ImageBGR]], created_at: datetime) -> Path:
        """Escribe un conjunto de recortes etiquetados para reentrenar el OCR.

        Precondiciones:
            `created_at` en UTC; cada texto cumple `PLATE_TEXT_REGEX`.

        Postcondiciones:
            Directorio nuevo con los PNG y su `annotations.csv`, en modo 0600/0700.

        Raises:
            ExportError: si un texto es inválido, ya existe el directorio o falla la escritura.
        """
        ...

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra las exportaciones de entrenamiento anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            Exportaciones anteriores a `cutoff` borradas; devuelve cuántas.

        Raises:
            ExportError: si falla el borrado.
        """
        ...


class LegibilityLabel(StrEnum):
    """Clase de legibilidad de un recorte para el filtro de proximidad."""

    LEGIBLE = "legible"
    BLURRY = "borrosa"
    NOT_PLATE = "no_placa"


@dataclass(frozen=True, slots=True)
class LegibilitySample:
    """Recorte etiquetado por legibilidad, sin texto de placa (SEG-07)."""

    image: ImageBGR
    label: LegibilityLabel
    status: ReviewStatus
    human_reviewed: bool
    video_group: int
    run_id: int
    track_id: int
    vehicle_type: VehicleType
    confidence: float
    agreement: float
    num_readings: int
    reasons: tuple[UnverifiedReason, ...]
    plate_width_px: int | None = None
    plate_height_px: int | None = None
    sharpness: float | None = None
    contrast: float | None = None
    frame_width: int | None = None
    frame_height: int | None = None

    def __post_init__(self) -> None:
        """Valida los identificadores, el grupo de video y el número de lecturas.

        Raises:
            InvalidEntityError: si `video_group` o `run_id` son `< 1`, o si `track_id`
                o `num_readings` son negativos.
        """
        if self.video_group < 1:
            raise InvalidEntityError(f"video_group debe ser >= 1: {self.video_group}")
        if self.run_id < 1:
            raise InvalidEntityError(f"run_id debe ser >= 1: {self.run_id}")
        if self.track_id < 0:
            raise InvalidEntityError(f"track_id debe ser >= 0: {self.track_id}")
        if self.num_readings < 0:
            raise InvalidEntityError(f"num_readings debe ser >= 0: {self.num_readings}")


class LegibilityExportStore(Protocol):
    """Escribe el dataset de legibilidad y limpia las exportaciones vencidas."""

    def write_samples(self, samples: Sequence[LegibilitySample], created_at: datetime) -> Path:
        """Escribe un conjunto de recortes etiquetados por legibilidad.

        Precondiciones:
            `created_at` en UTC.

        Postcondiciones:
            Directorio nuevo con los PNG y su `annotations.csv`, en modo 0600/0700.

        Raises:
            ExportError: si ya existe el directorio o falla la escritura.
        """
        ...

    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra las exportaciones de legibilidad anteriores al corte.

        Precondiciones:
            `cutoff` en UTC.

        Postcondiciones:
            Exportaciones anteriores a `cutoff` borradas; devuelve cuántas.

        Raises:
            ExportError: si falla el borrado.
        """
        ...


class KeyProvider(Protocol):
    """Entrega la clave maestra de cifrado."""

    def master_key(self) -> bytes:
        """Devuelve la clave maestra de 32 bytes.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            32 bytes.

        Raises:
            KeyUnavailableError: si la clave no está en el llavero del sistema.
        """
        ...


class ModelRegistry(Protocol):
    """Resuelve rutas locales de modelos verificados."""

    def verified_path(self, model_id: str) -> Path:
        """Devuelve la ruta verificada del modelo.

        Precondiciones:
            `model_id` en el manifiesto.

        Postcondiciones:
            Ruta existente cuyo SHA-256 coincide.

        Raises:
            ModelIntegrityError: si el archivo falta o el hash no coincide.
        """
        ...


class ReviewUI(Protocol):
    """Presenta avistamientos al operador y recoge su decisión."""

    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision:
        """Muestra un avistamiento y pide una decisión.

        Precondiciones:
            `record` con su `crop_ref` disponible si `crop` no es `None`.

        Postcondiciones:
            Decisión del operador para ese registro.

        Raises:
            ReviewError: si falla la interacción con el operador.
        """
        ...

    def close(self) -> None:
        """Cierra la interfaz de revisión.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Interfaz cerrada; idempotente.
        """
        ...


class Clock(Protocol):
    """Fuente de la hora actual."""

    def now(self) -> datetime:
        """Devuelve la hora actual.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            `datetime` con `tzinfo=UTC`.
        """
        ...


class RunStatus(StrEnum):
    """Estado de una corrida de procesamiento."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Resumen de una corrida tal como lo expone el navegador de avistamientos."""

    run_id: int
    profile: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    frames_processed: int | None
    sightings_confirmed: int | None
    sightings_unverified: int | None
    tracks_without_reading: int | None
    processing_ms: int | None


@dataclass(frozen=True, slots=True)
class SightingQuery:
    """Filtros de solo lectura para buscar avistamientos."""

    status: ReviewStatus | None = None
    plate_prefix: str | None = None
    run_id: int | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    include_duplicates: bool = False
    low_quality: LowQualityFilter = "include"

    def __post_init__(self) -> None:
        """Valida el prefijo, el identificador de corrida y el rango de fechas.

        Raises:
            InvalidEntityError: si el prefijo no cumple `PLATE_TEXT_REGEX`, el `run_id` es
                `< 1`, alguna fecha carece de zona horaria o el rango está invertido.
        """
        if self.plate_prefix is not None and PLATE_TEXT_REGEX.fullmatch(self.plate_prefix) is None:
            raise InvalidEntityError("plate_prefix inválido")
        if self.run_id is not None and self.run_id < 1:
            raise InvalidEntityError("run_id debe ser >= 1")
        for value in (self.created_from, self.created_to):
            if value is not None and value.tzinfo is None:
                raise InvalidEntityError("las fechas del rango deben tener zona horaria")
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_to <= self.created_from
        ):
            raise InvalidEntityError("created_to debe ser posterior a created_from")
        if self.low_quality not in ("include", "exclude", "only"):
            raise InvalidEntityError("low_quality inválido")


class SightingBrowser(Protocol):
    """Consulta de solo lectura de avistamientos y corridas."""

    def search_sightings(
        self, query: SightingQuery, limit: int, offset: int
    ) -> list[SightingRecord]:
        """Busca avistamientos combinando los filtros de `query`.

        Precondiciones:
            `1 <= limit <= 10000`; `offset >= 0`.

        Postcondiciones:
            Filtros combinados con AND; orden `sighting_id` descendente.

        Raises:
            RepositoryError: si la paginación es inválida o la consulta falla.
        """
        ...

    def count_sightings(self, query: SightingQuery) -> int:
        """Cuenta los avistamientos que devolvería la búsqueda sin paginar.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Total de filas que satisfacen `query`.

        Raises:
            RepositoryError: si la consulta falla.
        """
        ...

    def list_runs(self, limit: int, offset: int) -> list[RunRecord]:
        """Lista las corridas registradas, de la más reciente a la más antigua.

        Precondiciones:
            `1 <= limit <= 10000`; `offset >= 0`.

        Postcondiciones:
            Corridas ordenadas por `run_id` descendente.

        Raises:
            RepositoryError: si la paginación es inválida o la consulta falla.
        """
        ...

    def count_duplicates(self, sighting_ids: Sequence[int]) -> dict[int, int]:
        """Cuenta, por avistamiento, cuántos avistamientos lo tienen como `duplicate_of`.

        Precondiciones:
            Ninguna.

        Postcondiciones:
            Solo aparecen los ids de `sighting_ids` con al menos un duplicado.

        Raises:
            RepositoryError: si la consulta falla.
        """
        ...


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """Avance del procesamiento de un video, tal como se reporta al operador."""

    frames_decoded: int
    frames_processed: int
    position_ms: int
    duration_ms: int | None
    sightings_saved: int

    def __post_init__(self) -> None:
        """Valida que los contadores y la posición sean no negativos.

        Raises:
            InvalidEntityError: si algún contador o `position_ms` es negativo, o si
                `duration_ms` es negativo.
        """
        for name, value in (
            ("frames_decoded", self.frames_decoded),
            ("frames_processed", self.frames_processed),
            ("position_ms", self.position_ms),
            ("sightings_saved", self.sightings_saved),
        ):
            if value < 0:
                raise InvalidEntityError(f"{name} debe ser >= 0: {value}")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise InvalidEntityError(f"duration_ms debe ser >= 0: {self.duration_ms}")

    @property
    def fraction(self) -> float | None:
        """Fracción del video procesada, o `None` si no se conoce su duración."""
        if self.duration_ms is None or self.duration_ms == 0:
            return None
        return min(1.0, self.position_ms / self.duration_ms)


class ProgressReporter(Protocol):
    """Informa del avance del procesamiento y responde a las cancelaciones."""

    def report(self, update: ProgressUpdate) -> None:
        """Recibe el avance acumulado de una corrida de procesamiento.

        Precondiciones:
            Se llama desde el hilo que ejecuta `ProcessVideo`, con contadores no decrecientes.

        Postcondiciones:
            El avance queda comunicado al operador; el método retorna rápido y no lanza.
        """
        ...

    def cancel_requested(self) -> bool:
        """Indica si el operador pidió cancelar el procesamiento.

        Precondiciones:
            Ninguna; puede llamarse desde cualquier hilo.

        Postcondiciones:
            `True` desde que se pidió cancelar y mientras siga vigente esa petición.
        """
        ...


def _require_utc(value: datetime, name: str) -> None:
    """Exige un datetime con zona horaria UTC."""
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InvalidEntityError(f"{name} debe ser UTC con zona horaria")


def _counters(stats: RunStats) -> tuple[int, ...]:
    """Extrae los conteos enteros de un `RunStats`."""
    return (
        stats.frames_decoded,
        stats.frames_processed,
        stats.tracks_total,
        stats.sightings_confirmed,
        stats.sightings_unverified,
        stats.tracks_without_reading,
        stats.processing_ms,
    )
