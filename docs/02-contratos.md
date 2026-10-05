# 02 — Contratos: entidades, puertos, casos de uso y errores

> Fuente de verdad de las **firmas**. Si una firma cambia, se actualiza este archivo junto con el código.
> Todos los módulos empiezan con `from __future__ import annotations`.

## 1. Dominio — `src/lector_placas/domain/errors.py`

```python
class LectorPlacasError(Exception):
    """Raíz de todas las excepciones del proyecto."""

# --- Dominio ---
class DomainError(LectorPlacasError): ...
class InvalidBoundingBoxError(DomainError): ...
class InvalidConfidenceError(DomainError): ...
class InvalidPlateTextError(DomainError): ...
class InvalidEntityError(DomainError): ...          # ids negativos, tiempos inválidos, tz ausente, etc.
class PlateFormatCatalogError(DomainError): ...
class ConsolidationError(DomainError): ...

# --- Aplicación / infraestructura / adaptadores ---
class ConfigurationError(LectorPlacasError): ...
class InputValidationError(LectorPlacasError): ...
class UnsafePathError(InputValidationError): ...
class VideoSourceError(LectorPlacasError): ...
class ModelIntegrityError(LectorPlacasError): ...
class ModelLoadError(LectorPlacasError): ...
class ModelFetchError(LectorPlacasError): ...
class InferenceError(LectorPlacasError): ...
class TrackingError(LectorPlacasError): ...
class RepositoryError(LectorPlacasError): ...
class SightingNotFoundError(RepositoryError): ...
class CropStoreError(LectorPlacasError): ...
class CropNotFoundError(CropStoreError): ...
class ExportError(LectorPlacasError): ...
class EncryptionError(LectorPlacasError): ...
class KeyUnavailableError(LectorPlacasError): ...
class NetworkAccessError(LectorPlacasError): ...
class ReviewError(LectorPlacasError): ...
class EvaluationError(LectorPlacasError): ...
class DatasetError(LectorPlacasError): ...
class ProcessingCancelledError(LectorPlacasError): ...   # el operador canceló `ProcessVideo`
```

Cada clase tiene un docstring de una línea en español. No añaden atributos.

## 2. Dominio — `src/lector_placas/domain/entities.py`

```python
PLATE_TEXT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{1,10}$")
CROP_REF_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{32}$")

class VehicleType(StrEnum):
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    BUS = "bus"
    TRUCK = "truck"

class ReviewStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    ILLEGIBLE = "illegible"      # es una placa, pero no se puede leer

class UnverifiedReason(StrEnum):
    INSUFFICIENT_READINGS = "insufficient_readings"
    LOW_CONFIDENCE = "low_confidence"
    LOW_AGREEMENT = "low_agreement"
    UNRECOGNIZED_FORMAT = "unrecognized_format"
    UNVERIFIED_FORMAT = "unverified_format"
    VEHICLE_FORMAT_MISMATCH = "vehicle_format_mismatch"
    AMBIGUOUS_FORMAT = "ambiguous_format"
    CORRECTION_CONFLICT = "correction_conflict"   # (ADR-007 paso 5b)

@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Caja alineada a ejes en píxeles, esquina superior izquierda (x1, y1) e inferior derecha (x2, y2)."""
    x1: float
    y1: float
    x2: float
    y2: float
    # __post_init__: todos finitos, x1 >= 0, y1 >= 0, x2 > x1, y2 > y1; si no -> InvalidBoundingBoxError
    @property
    def width(self) -> float: ...
    @property
    def height(self) -> float: ...
    @property
    def area(self) -> float: ...
    def translate(self, dx: float, dy: float) -> BoundingBox: ...
    def clip(self, frame_width: int, frame_height: int) -> BoundingBox | None: ...
    def expand(self, ratio: float, frame_width: int, frame_height: int) -> BoundingBox | None: ...

@dataclass(frozen=True, slots=True)
class VehicleDetection:
    box: BoundingBox
    confidence: float            # [0, 1]
    vehicle_type: VehicleType

@dataclass(frozen=True, slots=True)
class PlateDetection:
    box: BoundingBox             # en coordenadas de la imagen que recibió el detector
    confidence: float            # [0, 1]

@dataclass(frozen=True, slots=True)
class TrackedVehicle:
    track_id: int                # >= 0
    box: BoundingBox
    confidence: float            # [0, 1]
    vehicle_type: VehicleType

@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str                            # ^[A-Z0-9]{0,10}$ (vacío = el OCR no produjo lectura válida)
    char_confidences: tuple[float, ...]  # len == len(text), cada valor en [0, 1]

@dataclass(frozen=True, slots=True)
class PlateReading:
    track_id: int                        # >= 0
    frame_index: int                     # >= 0
    timestamp_ms: int                    # >= 0
    text: str                            # PLATE_TEXT_REGEX
    char_confidences: tuple[float, ...]  # len == len(text), [0, 1]
    plate_box: BoundingBox               # coordenadas del frame
    detection_confidence: float          # [0, 1]
    quality_score: float                 # >= 0 (nitidez)
    @property
    def mean_confidence(self) -> float: ...

@dataclass(frozen=True, slots=True)
class PlateFormat:
    format_id: str                       # ^[a-z0-9_]{1,64}$
    category: str                        # no vacío
    pattern: str                         # ^[LD]{1,10}$  (L = letra, D = dígito)
    regex: str                           # debe compilar; se evalúa con re.fullmatch
    verified: bool
    vehicle_types: frozenset[VehicleType]  # no vacío
    source: str                          # no vacío
    def matches(self, text: str) -> bool: ...

@dataclass(frozen=True, slots=True)
class ConsolidatedPlate:
    text: str                            # PLATE_TEXT_REGEX
    confidence: float                    # [0, 1]
    agreement: float                     # [0, 1]
    num_readings: int                    # >= 1
    status: ReviewStatus                 # solo CONFIRMED o UNVERIFIED
    reasons: tuple[UnverifiedReason, ...]  # vacío <=> CONFIRMED; sin duplicados
    format_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class Sighting:
    run_id: int                          # >= 1
    track_id: int                        # >= 0
    first_seen_ms: int                   # >= 0
    last_seen_ms: int                    # >= first_seen_ms
    vehicle_type: VehicleType
    plate: ConsolidatedPlate
    crop_ref: str | None                 # None o CROP_REF_REGEX
    created_at: datetime                 # con tzinfo, UTC
    quality: CropQuality | None = None
@dataclass(frozen=True, slots=True)
class CropQuality:                       # medidas del mejor recorte
    plate_width_px: int                  # >= 1
    plate_height_px: int                 # >= 1
    sharpness: float                     # finito, >= 0 (varianza del Laplaciano, ImageQualityScorer)
    contrast: float                      # finito, >= 0 (rms_contrast: std de la luminancia 0.114B+0.587G+0.299R)

@dataclass(frozen=True, slots=True)
class SightingRecord:
    sighting_id: int
    run_id: int
    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    ocr_text: str                        # texto consolidado original
    plate_text: str                      # texto vigente (corregido si status == CORRECTED)
    confidence: float
    agreement: float
    num_readings: int
    status: ReviewStatus
    reasons: tuple[UnverifiedReason, ...]
    format_ids: tuple[str, ...]
    crop_ref: str | None
    created_at: datetime
    reviewed_at: datetime | None
    quality: CropQuality | None = None
    duplicate_of: int | None = None      # (columna) / 061 (lógica); >= 1 y != sighting_id
```

`BoundingBox.clip` recorta a `[0, frame_width] × [0, frame_height]` y devuelve `None` si queda vacía.
`BoundingBox.expand(ratio, w, h)` agranda cada lado `ratio * width` (horizontal) y `ratio * height`
(vertical), luego aplica `clip`. `ratio` debe estar en `[0, 1]` o lanza `InvalidBoundingBoxError`.

## 3. Dominio — otros módulos

`domain/plate_formats.py`
```python

class PlateFormatCatalog:
    def __init__(self, formats: Sequence[PlateFormat]) -> None: ...  # vacío o ids repetidos -> PlateFormatCatalogError
    @property
    def formats(self) -> tuple[PlateFormat, ...]: ...
    def patterns_of_length(self, length: int) -> tuple[str, ...]: ...  # patrones distintos, orden alfabético
    def matching(self, text: str) -> tuple[PlateFormat, ...]: ...     # orden del catálogo
    def matching_with_pattern(self, text: str, pattern: str) -> tuple[PlateFormat, ...]: ...
```

`domain/ocr_correction.py`
```python
@dataclass(frozen=True, slots=True)
class ConfusionMap:
    pairs: tuple[tuple[str, str], ...]   # (letra, dígito); letra ^[A-Z]$, dígito ^[0-9]$, sin repetidos
    @classmethod
    def default(cls) -> ConfusionMap: ...  # (("O","0"), ("I","1"), ("B","8"), ("S","5"))
    def to_digit(self, char: str) -> str: ...
    def to_letter(self, char: str) -> str: ...

def correct_to_pattern(text: str, pattern: str, confusions: ConfusionMap) -> str: ...
```

`domain/consolidation.py`
```python
@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    min_readings: int          # >= 1
    confirm_threshold: float   # [0, 1]
    min_agreement: float       # [0, 1]
    ambiguity_margin: float    # [0, 1]

class VotingPlateConsolidator:
    def __init__(self, catalog: PlateFormatCatalog, policy: ConsolidationPolicy,
                 confusions: ConfusionMap) -> None: ...
    def consolidate(self, readings: Sequence[PlateReading],
                    vehicle_type: VehicleType) -> ConsolidatedPlate: ...
```
Algoritmo normativo: ADR-007.

`domain/privacy.py`
```python
def mask_plate(text: str) -> str: ...
# len <= 2 -> "*" * len; si no -> text[0] + "*" * (len - 2) + text[-1].  "ABC123" -> "A****3"
```

## 4. Aplicación — `src/lector_placas/application/ports.py`

```python
ImageBGR: TypeAlias = npt.NDArray[np.uint8]   # (alto, ancho, 3), BGR

@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    index: int            # >= 0, índice entre los frames decodificados
    timestamp_ms: int     # >= 0, relativo al primer frame
    image: ImageBGR       # ndim == 3, shape[2] == 3, dtype uint8, ya rotado (upright)
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...

@dataclass(frozen=True, slots=True)
class VideoInfo:
    width: int                 # > 0, tras aplicar rotación
    height: int                # > 0, tras aplicar rotación
    rotation_deg: int          # 0, 90, 180 o 270
    duration_ms: int | None    # >= 0 o None
    average_fps: float | None  # > 0 o None
    codec: str

@dataclass(frozen=True, slots=True)
class RunStart:
    video_sha256: str          # ^[0-9a-f]{64}$
    profile: str
    video: VideoInfo
    started_at: datetime       # UTC

@dataclass(frozen=True, slots=True)
class RunStats:
    frames_decoded: int
    frames_processed: int
    tracks_total: int
    sightings_confirmed: int
    sightings_unverified: int
    tracks_without_reading: int
    processing_ms: int
    video_duration_ms: int | None
    @property
    def speed_factor(self) -> float | None: ...  # video_duration_ms / processing_ms; None si falta o processing_ms == 0

@dataclass(frozen=True, slots=True)
class RecordPurge:
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    crop_refs: tuple[str, ...]   # recortes de los avistamientos borrados que aún existían

class AuditEvent(StrEnum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    REVIEW = "review"
    PURGE = "purge"
    EXPORT = "export"

class ReviewAction(StrEnum):
    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    SKIP = "skip"
    QUIT = "quit"
    ILLEGIBLE = "illegible"      # → ReviewStatus.ILLEGIBLE

@dataclass(frozen=True, slots=True)
class ReviewDecision:
    action: ReviewAction
    corrected_text: str | None = None   # obligatorio (PLATE_TEXT_REGEX) solo si action == CORRECT; None en otro caso

class VideoSource(Protocol):
    def info(self) -> VideoInfo: ...
    def frames(self) -> Iterator[Frame]: ...
    def close(self) -> None: ...

class VideoSourceFactory(Protocol):
    def open(self, path: Path) -> VideoSource: ...

class FrameSampler(Protocol):
    def should_process(self, timestamp_ms: int) -> bool: ...
    def reset(self) -> None: ...

class VehicleDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[VehicleDetection]: ...

class PlateDetector(Protocol):
    def detect(self, image: ImageBGR) -> list[PlateDetection]: ...

class Tracker(Protocol):
    def update(self, detections: Sequence[VehicleDetection], image: ImageBGR,
               timestamp_ms: int) -> list[TrackedVehicle]: ...
    def reset(self) -> None: ...

class PlateReader(Protocol):
    def read(self, plate_images: Sequence[ImageBGR]) -> list[OcrResult]: ...

class ImageQualityScorer(Protocol):
    def sharpness(self, image: ImageBGR) -> float: ...

class PlateConsolidator(Protocol):
    def consolidate(self, readings: Sequence[PlateReading],
                    vehicle_type: VehicleType) -> ConsolidatedPlate: ...

class PlateRepository(Protocol):
    def start_run(self, run: RunStart) -> int: ...
    def finish_run(self, run_id: int, stats: RunStats, finished_at: datetime,
                   succeeded: bool) -> None: ...
    def save_sighting(self, sighting: Sighting) -> int: ...
    def list_sightings(self, status: ReviewStatus | None, limit: int,
                       offset: int) -> list[SightingRecord]: ...
    def get_sighting(self, sighting_id: int) -> SightingRecord: ...
    def record_review(self, sighting_id: int, status: ReviewStatus,
                      corrected_text: str | None, reviewed_at: datetime) -> None: ...
        # status ∈ {CONFIRMED, CORRECTED, REJECTED, ILLEGIBLE}; ILLEGIBLE se trata como REJECTED
    def expire_crop_refs(self, cutoff: datetime) -> list[str]: ...
    def delete_records_before(self, cutoff: datetime) -> RecordPurge: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
    def run_video_hashes(self) -> dict[int, str]: ...   # run_id → video_sha256 de todas las corridas
    def run_frame_sizes(self) -> dict[int, tuple[int, int]]: ...   # run_id → (width, height) ya rotados
    def mark_duplicates(self, pairs: Sequence[tuple[int, int]]) -> None: ...   # (duplicado, conservado), una transacción
    def close(self) -> None: ...

class CropStore(Protocol):
    def save(self, image: ImageBGR) -> str: ...
    def load(self, crop_ref: str) -> ImageBGR: ...
    def delete(self, crop_ref: str) -> None: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...

class ExportStore(Protocol):
    def write_sightings(self, records: Sequence[SightingRecord], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...

class TrainingExportStore(Protocol):
    def write_samples(self, samples: Sequence[tuple[str, ImageBGR]], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...


class LegibilityLabel(StrEnum):
    LEGIBLE = "legible"
    BLURRY = "borrosa"
    NOT_PLATE = "no_placa"

@dataclass(frozen=True, slots=True)
class LegibilitySample:            # sin texto de placa (SEG-07)
    image: ImageBGR
    label: LegibilityLabel
    status: ReviewStatus
    human_reviewed: bool           # reviewed_at is not None
    video_group: int               # >= 1; corridas del mismo video comparten grupo
    run_id: int
    track_id: int
    vehicle_type: VehicleType
    confidence: float
    agreement: float
    num_readings: int
    reasons: tuple[UnverifiedReason, ...]
    plate_width_px: int | None = None    # (las seis)
    plate_height_px: int | None = None
    sharpness: float | None = None
    contrast: float | None = None
    frame_width: int | None = None
    frame_height: int | None = None

class LegibilityExportStore(Protocol):
    def write_samples(self, samples: Sequence[LegibilitySample], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...

class KeyProvider(Protocol):
    def master_key(self) -> bytes: ...

class ModelRegistry(Protocol):
    def verified_path(self, model_id: str) -> Path: ...

class ReviewUI(Protocol):
    def ask(self, record: SightingRecord, crop: ImageBGR | None) -> ReviewDecision: ...
    def close(self) -> None: ...

class Clock(Protocol):
    def now(self) -> datetime: ...

# --- Progreso y búsqueda (los usa la web) ---
@dataclass(frozen=True, slots=True)
class ProgressUpdate:                   # todos los enteros >= 0; si no → InvalidEntityError
    frames_decoded: int
    frames_processed: int
    position_ms: int                    # timestamp del último frame decodificado
    duration_ms: int | None             # VideoInfo.duration_ms
    sightings_saved: int                # confirmados + sin verificar guardados hasta ahora
    @property
    def fraction(self) -> float | None: ...   # min(1, position_ms / duration_ms); None si duration_ms es None o 0

class ProgressReporter(Protocol):
    def report(self, update: ProgressUpdate) -> None: ...
    def cancel_requested(self) -> bool: ...

class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class RunRecord:
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
class SightingQuery:                    # validación en __post_init__ → InvalidEntityError
    status: ReviewStatus | None = None
    plate_prefix: str | None = None     # ^[A-Z0-9]{1,10}$; compara con el inicio de plate_text
    run_id: int | None = None           # >= 1
    created_from: datetime | None = None   # con tzinfo; inclusivo
    created_to: datetime | None = None     # con tzinfo; exclusivo; > created_from si ambos
    include_duplicates: bool = False       # por defecto excluye duplicate_of no nulo

class SightingBrowser(Protocol):
    def search_sightings(self, query: SightingQuery, limit: int, offset: int) -> list[SightingRecord]: ...
    def count_sightings(self, query: SightingQuery) -> int: ...
    def list_runs(self, limit: int, offset: int) -> list[RunRecord]: ...
```

### Pre/postcondiciones de los puertos

| Puerto.método | Precondiciones | Postcondiciones | Raises |
|---|---|---|---|
| `VideoSourceFactory.open` | `path` ya validado | Fuente abierta; `info()` disponible | `VideoSourceError` si no decodifica o no tiene stream de video |
| `FrameGrabber.grab` | `path` localizado por `VideoLocator`; `timestamp_ms >= 0` | Imagen BGR upright del primer frame con timestamp `>= timestamp_ms` (o el último) | `VideoSourceError` si no abre o no decodifica |
| `VideoSource.frames` | Fuente abierta; se llama una sola vez | `Frame` en orden de decodificación, `timestamp_ms` no decreciente, imagen upright BGR | `VideoSourceError` ante error de decodificación |
| `VideoSource.close` | — | Idempotente; libera el contenedor | — |
| `FrameSampler.should_process` | `timestamp_ms >= 0` | `True` para el primer frame; luego según ADR-006 | — |
| `VehicleDetector.detect` | Imagen BGR válida | Cajas dentro de la imagen, `confidence >= umbral` configurado, solo 4 tipos | `InferenceError` |
| `PlateDetector.detect` | Imagen BGR con lados ≥ 16 px | Cajas en coordenadas de esa imagen, ordenadas por confianza descendente | `InferenceError` |
| `Tracker.update` | `timestamp_ms` no decreciente entre llamadas | Solo `track_id >= 0`; cada salida corresponde a una detección de entrada | `TrackingError` |
| `Tracker.reset` | — | Estado vacío; IDs reinician en 0 | — |
| `PlateReader.read` | Lista (posiblemente vacía) de imágenes BGR | Misma longitud y orden que la entrada | `InferenceError` |
| `ImageQualityScorer.sharpness` | Imagen BGR no vacía | Valor finito ≥ 0 | — |
| `PlateConsolidator.consolidate` | ≥ 1 lectura, todas del mismo `track_id` | `ConsolidatedPlate` válido | `ConsolidationError` |
| `PlateRepository.start_run` | BD abierta | `run_id >= 1`; corrida en estado `running` | `RepositoryError` |
| `PlateRepository.save_sighting` | `sighting.run_id` existe | Fila insertada; si CONFIRMED, placa enlazada en `plates` | `RepositoryError` |
| `PlateRepository.get_sighting` | — | Registro | `SightingNotFoundError` |
| `PlateRepository.record_review` | `status ∈ {CONFIRMED, CORRECTED, REJECTED}`; `corrected_text` solo con CORRECTED | Estado, `plate_text`, `plate_id`, `reviewed_at` actualizados | `SightingNotFoundError`, `RepositoryError` |
| `CropStore.save` | Imagen BGR no vacía | `crop_ref` de 32 hex; archivo cifrado 0600 | `CropStoreError`, `EncryptionError` |
| `CropStore.load` | `crop_ref` válido | Imagen idéntica píxel a píxel a la guardada | `CropNotFoundError`, `EncryptionError` |
| `CropStore.delete` | `crop_ref` válido | Archivo inexistente; idempotente | `CropStoreError` |
| `CropStore.delete_older_than` | `cutoff` UTC | Borra archivos de recorte con fecha de modificación < `cutoff` (huérfanos incluidos); devuelve cuántos | `CropStoreError` |
| `ExportStore.write_sightings` | — | CSV nuevo 0600 en el directorio de exportaciones | `ExportError` |
| `KeyProvider.master_key` | — | 32 bytes | `KeyUnavailableError` |
| `ModelRegistry.verified_path` | `model_id` en el manifiesto | Ruta existente cuyo SHA-256 coincide | `ModelIntegrityError` |
| `Clock.now` | — | `datetime` con `tzinfo=UTC` | — |
| `ProgressReporter.report` | Se llama desde el hilo que ejecuta `ProcessVideo` | Retorna rápido; no lanza | — |
| `ProgressReporter.cancel_requested` | Puede llamarse desde cualquier hilo | `True` desde que se pidió cancelar | — |
| `SightingBrowser.search_sightings` | `1 <= limit <= 10000`, `offset >= 0` | Filtros combinados con AND; orden `sighting_id` descendente | `RepositoryError` |
| `SightingBrowser.count_sightings` | — | Total que devolvería la búsqueda sin paginar | `RepositoryError` |
| `SightingBrowser.list_runs` | `1 <= limit <= 10000`, `offset >= 0` | Orden `run_id` descendente | `RepositoryError` |

## 5. Aplicación — casos de uso y servicios

`application/frame_sampler.py`
```python
class TimeBasedFrameSampler:
    def __init__(self, target_fps: float) -> None: ...   # target_fps > 0 o ConfigurationError
    def should_process(self, timestamp_ms: int) -> bool: ...
    def reset(self) -> None: ...
```

`application/image_ops.py`
```python
def crop_image(image: ImageBGR, box: BoundingBox) -> ImageBGR: ...
# filas floor(y1)..ceil(y2), columnas floor(x1)..ceil(x2), recortado a la imagen; devuelve copia C-contigua
```

`application/track_registry.py`
```python
@dataclass(frozen=True, slots=True, eq=False)
class FinalizedTrack:
    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    readings: tuple[PlateReading, ...]
    best_crop: ImageBGR | None

class TrackRegistry:
    def __init__(self, max_readings_per_track: int) -> None: ...
    def observe(self, tracked: Sequence[TrackedVehicle], timestamp_ms: int) -> None: ...
    def needs_reading(self, track_id: int) -> bool: ...   # True <=> el track está activo: y no resuelto
    def readings(self, track_id: int) -> tuple[PlateReading, ...]: ...   # orden (timestamp_ms, frame_index)
    def vehicle_type(self, track_id: int) -> VehicleType: ...            # tipo dominante actual
    def mark_resolved(self, track_id: int) -> None: ...
    def is_full(self, track_id: int) -> bool: ...         # activo y con max_readings_per_track lecturas
    def add_reading(self, reading: PlateReading, crop: ImageBGR) -> None: ...
        # lleno → reemplaza a la peor si (ancho de placa, nitidez) es estrictamente mayor;
        # readings de FinalizedTrack en orden (timestamp_ms, frame_index)
    def pop_inactive(self, now_ms: int, inactive_after_ms: int) -> list[FinalizedTrack]: ...
    def pop_all(self) -> list[FinalizedTrack]: ...
```

`application/process_video.py`
```python
@dataclass(frozen=True, slots=True)
class ProcessingSettings:
    profile_name: str
    max_ocr_per_frame: int          # >= 1
    min_plate_width_px: int         # >= 1
    min_sharpness: float            # >= 0
    vehicle_crop_margin: float      # [0, 1]
    track_finalize_after_ms: int    # >= 1
    max_readings_per_track: int     # >= 1
    near_min_width_frac: float = 0.0                    # [0, 0.2]
    max_plate_vehicle_ratio: float = 1.0                # (0, 1]
    roi: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)   # 0 <= x1 < x2 <= 1, 0 <= y1 < y2 <= 1
    early_stop: bool = False
    dedup_window_ms: int = 0                            # [0, 600000]; 0 desactiva

# application/duplicates.py: DuplicateCandidate(sighting_id, plate_text, status, confidence,
#   first_seen_ms, last_seen_ms); find_duplicates(candidates, window_ms) -> list[(duplicado, conservado)]
#   conservado = min por (no CONFIRMED, -confidence, sighting_id); grupo por texto exacto y hueco <= window_ms

# application/proximity.py: FRAME_EDGE_MARGIN_PX = 2; effective_min_width(w, h, min_px, frac) -> int
#   = ceil(round(max(min_px, frac * max(w, h)), 6)); center_in_roi(box, roi, w, h) -> bool;
#   touches_frame_edge(box, w, h) -> bool; validate_roi(roi) -> None; ProximityCounters

@dataclass(frozen=True, slots=True)
class PipelineDependencies:
    source_factory: VideoSourceFactory
    sampler: FrameSampler
    vehicle_detector: VehicleDetector
    plate_detector: PlateDetector
    tracker: Tracker
    reader: PlateReader
    quality: ImageQualityScorer
    consolidator: PlateConsolidator
    repository: PlateRepository
    crop_store: CropStore
    clock: Clock

@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: int
    stats: RunStats

class ProcessVideo:
    def __init__(self, deps: PipelineDependencies, settings: ProcessingSettings) -> None: ...
    def execute(
        self, video_path: Path, video_sha256: str, progress: ProgressReporter | None = None
    ) -> RunResult: ...
```

`application/purge_expired.py`
```python
@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    crops_days: int      # >= 1
    records_days: int    # >= crops_days

@dataclass(frozen=True, slots=True)
class PurgeResult:
    crops_deleted: int
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    exports_deleted: int

class PurgeExpiredData:
    def __init__(self, repository: PlateRepository, crop_store: CropStore,
                 export_store: ExportStore, clock: Clock, policy: RetentionPolicy) -> None: ...
    def execute(self) -> PurgeResult: ...
```

`application/export_sightings.py`
```python
class ExportSightings:
    def __init__(self, repository: PlateRepository, export_store: ExportStore, clock: Clock) -> None: ...
    def execute(self, status: ReviewStatus | None) -> Path: ...
```

`application/review_sightings.py`
```python
@dataclass(frozen=True, slots=True)
class ReviewSummary:
    confirmed: int
    corrected: int
    rejected: int
    skipped: int
    illegible: int = 0
class ReviewSightings:
    def __init__(self, repository: PlateRepository, crop_store: CropStore, ui: ReviewUI,
                 clock: Clock) -> None: ...
    def execute(self, limit: int) -> ReviewSummary: ...
```

`application/export_reviewed.py`
```python
@dataclass(frozen=True, slots=True)
class ExportReviewedResult:
    path: Path
    exported: int
    skipped: int

class ExportReviewedCrops:
    def __init__(self, repository: PlateRepository, crop_store: CropStore,
                 training_store: TrainingExportStore, clock: Clock) -> None: ...
    def execute(self) -> ExportReviewedResult: ...
```
Cambios en `application/purge_expired.py`: `RetentionPolicy.training_days: int = 180`,
`PurgeResult.training_deleted: int = 0` y `PurgeExpiredData(..., policy, training_store: TrainingExportStore | None = None)`.

`application/export_legibility.py`
```python
LABELS: Final[dict[ReviewStatus, LegibilityLabel]]   # CONFIRMED/CORRECTED→LEGIBLE, ILLEGIBLE→BLURRY, REJECTED→NOT_PLATE

@dataclass(frozen=True, slots=True)
class ExportLegibilityResult:
    path: Path
    exported: int
    skipped: int
    per_label: dict[LegibilityLabel, int]

class ExportLegibilityDataset:
    def __init__(self, repository: PlateRepository, crop_store: CropStore,
                 legibility_store: LegibilityExportStore, clock: Clock) -> None: ...
    def execute(self) -> ExportLegibilityResult: ...
```
Cambio en la purga: `PurgeExpiredData(..., training_store=None, legibility_store: LegibilityExportStore | None = None)`;
lo que borra se suma a `training_deleted` (mismo corte `training_days`).

## 6. Infraestructura (firmas públicas)

```python
# infrastructure/clock.py
class SystemClock:
    def now(self) -> datetime: ...                      # datetime.now(UTC)

# infrastructure/paths.py
def resolve_within(base: Path, candidate: Path) -> Path: ...   # UnsafePathError si escapa de base
def ensure_private_dir(path: Path) -> Path: ...                # mkdir -p, chmod 0o700

# infrastructure/input_validation.py
def validate_video_path(path: Path, allowed_dirs: Sequence[Path], allowed_extensions: frozenset[str],
                        max_size_bytes: int) -> Path: ...
def sha256_file(path: Path) -> str: ...

# infrastructure/crypto.py
class KeyPurpose(StrEnum):
    SQLCIPHER = "lector-placas/sqlcipher/v1"
    CROPS = "lector-placas/crops/v1"
def derive_key(master_key: bytes, purpose: KeyPurpose) -> bytes: ...
def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes: ...
def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes: ...

# infrastructure/logging_setup.py
def redact_plates(text: str) -> str: ...
class PlateRedactionFilter(logging.Filter): ...
class RedactingFormatter(logging.Formatter): ...   # redacta también trazas de excepción
def configure_logging(level: str, log_file: Path) -> None: ...

# infrastructure/network_guard.py
def block_network() -> None: ...

# infrastructure/model_registry.py
class ManifestModelRegistry:
    def __init__(self, manifest_path: Path, models_dir: Path) -> None: ...
    def verified_path(self, model_id: str) -> Path: ...

# infrastructure/model_fetcher.py
def fetch_models(manifest_path: Path, models_dir: Path, opener: UrlOpener) -> list[str]: ...

# infrastructure/config.py
def load_config(path: Path) -> AppConfig: ...   # LECTOR_EXECUTION_PROVIDER (cpu|cuda) sustituye inference.execution_provider
```

## 7. Estrategia de errores

- Cada capa lanza solo subclases de `LectorPlacasError`. Los adaptadores traducen excepciones de
  librerías (`av.error.FFmpegError`, `onnxruntime` `RuntimeError`/`Fail`, `sqlcipher3.dbapi2.DatabaseError`,
  `cryptography.exceptions.InvalidTag`, `keyring.errors.KeyringError`, `OSError`) con `raise ... from e`.
- `ProcessVideo.execute` ante cualquier `LectorPlacasError`: registra `ERROR`, llama
  `finish_run(succeeded=False)` con las estadísticas parciales y relanza. Los avistamientos ya
  guardados se conservan. La cancelación sigue el mismo camino con `ProcessingCancelledError`: la corrida
  queda `failed` y los tracks aún abiertos se descartan.
- `cli/main.py` es el único que captura todo: mapea a códigos de salida:

| Excepción | Código |
|---|---|
| éxito | 0 |
| inesperada (cualquier otra) | 1 |
| `ConfigurationError` | 2 |
| `InputValidationError` (incl. `UnsafePathError`), `VideoSourceError` | 3 |
| `ModelIntegrityError`, `ModelLoadError`, `ModelFetchError` | 4 |
| `KeyUnavailableError`, `EncryptionError` | 5 |
| `RepositoryError`, `CropStoreError`, `ExportError` | 6 |
| `NetworkAccessError` | 7 |
| `EvaluationError`, `DatasetError` | 8 |

- Mensajes de error en español, sin texto de placa en claro (usar `mask_plate`), sin rutas absolutas
  del home del usuario en logs de nivel `INFO` o superior (solo nombres de archivo).

## 8. Estrategia de logging

- `configure_logging(level, log_file)`: handler de archivo `logs/lector.log` (creado 0600) y handler de
  `stderr`; formato `%(asctime)s %(levelname)s %(name)s %(message)s`; ambos con `PlateRedactionFilter`
  y `RedactingFormatter` (que redacta la salida final, incluidas las trazas de excepción).
- `PlateRedactionFilter` reemplaza en el mensaje ya formateado cualquier coincidencia de
  `(?<![A-Z0-9])(?:[A-Z]{3}[0-9]{2}[A-Z0-9]?|[0-9]{3}[A-Z]{3}|[A-Z]{2}[0-9]{4}|[RS][0-9]{5}|T[0-9]{4})(?![A-Z0-9])`
  por `mask_plate(coincidencia)`. Es defensa en profundidad: el código igualmente debe usar `mask_plate`.
- Eventos `INFO` por corrida: inicio (run_id, perfil, resolución, rotación), fin (RunStats), purga
  (conteos), exportación (nombre de archivo), revisión (conteos). Nunca frames, recortes ni claves.
