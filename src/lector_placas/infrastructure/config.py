"""Carga y validación de `config/lector.yaml` con pydantic (ADR-006, ADR-007)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from lector_placas.application.proximity import NEAR_MIN_WIDTH_FRAC_MAX
from lector_placas.domain.consolidation import ConsolidationPolicy
from lector_placas.domain.entities import PlateFormat, VehicleType
from lector_placas.domain.errors import ConfigurationError, DomainError
from lector_placas.domain.ocr_correction import ConfusionMap
from lector_placas.domain.plate_formats import PlateFormatCatalog

IDENTIFIER_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
PROFILE_NAME_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z_]{1,32}$")
INPUT_SIZE_MIN: Final[int] = 32
INPUT_SIZE_MAX: Final[int] = 1280
INPUT_SIZE_STEP: Final[int] = 32
EXTENSION_MIN_LENGTH: Final[int] = 2
EXTENSION_MAX_LENGTH: Final[int] = 10
TARGET_FPS_MAX: Final[float] = 120.0
DEDUP_WINDOW_MS_MAX: Final[int] = 600_000
RETENTION_MAX_DAYS: Final[int] = 3650


def _field_name(info: ValidationInfo) -> str:
    """Nombre del campo en validación, para los mensajes de error."""
    return info.field_name or "campo"


def _unit_interval(value: float, name: str) -> float:
    """Devuelve `value` si está en [0, 1]; si no, lanza `ValueError`."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} debe estar en [0, 1]: {value}")
    return value


def _at_least_one(value: int, name: str) -> int:
    """Devuelve `value` si es >= 1; si no, lanza `ValueError`."""
    if value < 1:
        raise ValueError(f"{name} debe ser >= 1: {value}")
    return value


def _non_negative(value: int, name: str) -> int:
    """Devuelve `value` si es >= 0; si no, lanza `ValueError`."""
    if value < 0:
        raise ValueError(f"{name} debe ser >= 0: {value}")
    return value


def _input_size(value: int, name: str) -> int:
    """Exige un tamaño de entrada múltiplo de 32 dentro de [32, 1280]."""
    if not INPUT_SIZE_MIN <= value <= INPUT_SIZE_MAX or value % INPUT_SIZE_STEP != 0:
        raise ValueError(f"{name} debe ser múltiplo de 32 en [32, 1280]: {value}")
    return value


def _relative_path(value: Path) -> Path:
    """Exige una ruta relativa sin componentes `..` (SEG-13)."""
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"la ruta debe ser relativa y sin '..': {value}")
    return value


def _extension(value: str) -> str:
    """Exige una extensión como `.mp4`: empieza por punto, en minúsculas, de 2 a 10 caracteres."""
    if (
        not value.startswith(".")
        or value != value.lower()
        or not EXTENSION_MIN_LENGTH <= len(value) <= EXTENSION_MAX_LENGTH
    ):
        raise ValueError(f"extensión de archivo inválida: {value!r}")
    return value


def _identifier(value: str, name: str) -> str:
    """Exige un identificador que cumpla `^[a-z0-9][a-z0-9-]{1,63}$`."""
    if IDENTIFIER_REGEX.fullmatch(value) is None:
        raise ValueError(f"{name} inválido: {value!r}")
    return value


class StrictModel(BaseModel):
    """Base de la configuración: inmutable y sin claves desconocidas."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PathsConfig(StrictModel):
    """Directorios de trabajo, relativos a la raíz del proyecto."""

    data_dir: Path
    models_dir: Path
    log_dir: Path
    model_manifest: Path

    @field_validator("data_dir", "models_dir", "log_dir", "model_manifest")
    @classmethod
    def _validate_paths(cls, value: Path) -> Path:
        """Rechaza rutas absolutas o con `..`."""
        return _relative_path(value)


class InputConfig(StrictModel):
    """Restricciones de los videos que se pueden procesar."""

    allowed_dirs: tuple[Path, ...] = Field(min_length=1)
    allowed_extensions: tuple[str, ...] = Field(min_length=1)
    max_file_size_mb: int = Field(ge=1, le=102400)

    @field_validator("allowed_dirs")
    @classmethod
    def _validate_allowed_dirs(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        """Rechaza rutas absolutas o con `..`."""
        for path in value:
            _relative_path(path)
        return value

    @field_validator("allowed_extensions")
    @classmethod
    def _validate_allowed_extensions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Valida cada extensión admitida."""
        for extension in value:
            _extension(extension)
        return value


class InferenceConfig(StrictModel):
    """Proveedor de ejecución de ONNX Runtime."""

    execution_provider: Literal["cuda", "cpu"]


class VehicleDetectorConfig(StrictModel):
    """Modelo y umbrales del detector de vehículos."""

    model_id: str
    input_size: int
    score_threshold: float

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str) -> str:
        """Exige un identificador de modelo válido."""
        return _identifier(value, "model_id")

    @field_validator("input_size")
    @classmethod
    def _validate_input_size(cls, value: int) -> int:
        """Exige un tamaño de entrada múltiplo de 32."""
        return _input_size(value, "input_size")

    @field_validator("score_threshold")
    @classmethod
    def _validate_score_threshold(cls, value: float) -> float:
        """Exige un umbral en [0, 1]."""
        return _unit_interval(value, "score_threshold")


class PlateDetectorConfig(StrictModel):
    """Backend, modelo y umbrales del detector de placas."""

    backend: Literal["open_image_models", "yolo"]
    model_id: str
    input_size: int
    score_threshold: float

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str) -> str:
        """Exige un identificador de modelo válido."""
        return _identifier(value, "model_id")

    @field_validator("input_size")
    @classmethod
    def _validate_input_size(cls, value: int) -> int:
        """Exige un tamaño de entrada múltiplo de 32."""
        return _input_size(value, "input_size")

    @field_validator("score_threshold")
    @classmethod
    def _validate_score_threshold(cls, value: float) -> float:
        """Exige un umbral en [0, 1]."""
        return _unit_interval(value, "score_threshold")


class OcrConfig(StrictModel):
    """Modelo y configuración del lector de placas."""

    model_id: str
    config_id: str

    @field_validator("model_id", "config_id")
    @classmethod
    def _validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
        """Exige identificadores válidos."""
        return _identifier(value, _field_name(info))


class ModelsConfig(StrictModel):
    """Modelos de detección de vehículos, detección de placas y OCR."""

    vehicle_detector: VehicleDetectorConfig
    plate_detector: PlateDetectorConfig
    ocr: OcrConfig


class TrackerConfig(StrictModel):
    """Parámetros de BoT-SORT y de la compensación de movimiento de cámara."""

    lost_track_buffer: int
    track_activation_threshold: float
    minimum_consecutive_frames: int
    minimum_iou_threshold_first_assoc: float
    minimum_iou_threshold_second_assoc: float
    minimum_iou_threshold_unconfirmed_assoc: float
    high_conf_det_threshold: float
    cmc_method: Literal["sparseOptFlow", "orb", "sift", "ecc"]
    cmc_downscale: int

    @field_validator("lost_track_buffer")
    @classmethod
    def _validate_lost_track_buffer(cls, value: int) -> int:
        """Exige un buffer no negativo."""
        return _non_negative(value, "lost_track_buffer")

    @field_validator("minimum_consecutive_frames", "cmc_downscale")
    @classmethod
    def _validate_minimums(cls, value: int, info: ValidationInfo) -> int:
        """Exige enteros >= 1."""
        return _at_least_one(value, _field_name(info))

    @field_validator(
        "track_activation_threshold",
        "minimum_iou_threshold_first_assoc",
        "minimum_iou_threshold_second_assoc",
        "minimum_iou_threshold_unconfirmed_assoc",
        "high_conf_det_threshold",
    )
    @classmethod
    def _validate_thresholds(cls, value: float, info: ValidationInfo) -> float:
        """Exige umbrales en [0, 1]."""
        return _unit_interval(value, _field_name(info))


class ProfileConfig(StrictModel):
    """Parámetros de proceso de un perfil de escenario (ADR-006)."""

    mode: Literal["estatico", "movil"]
    camera_motion_compensation: bool
    target_fps: float
    max_readings_per_track: int
    track_finalize_after_ms: int
    min_readings: int
    confirm_threshold: float
    min_agreement: float
    min_plate_width_px: int
    min_sharpness: float
    max_ocr_per_frame: int
    vehicle_crop_margin: float
    near_min_width_frac: float
    max_plate_vehicle_ratio: float
    roi: tuple[float, float, float, float]
    early_stop: bool
    dedup_window_ms: int

    @field_validator("target_fps")
    @classmethod
    def _validate_target_fps(cls, value: float) -> float:
        """Exige una tasa de muestreo en (0, 120]."""
        if not 0.0 < value <= TARGET_FPS_MAX:
            raise ValueError(f"target_fps debe estar en (0, 120]: {value}")
        return value

    @field_validator(
        "max_readings_per_track",
        "track_finalize_after_ms",
        "min_readings",
        "min_plate_width_px",
        "max_ocr_per_frame",
    )
    @classmethod
    def _validate_positive(cls, value: int, info: ValidationInfo) -> int:
        """Exige enteros >= 1."""
        return _at_least_one(value, _field_name(info))

    @field_validator("confirm_threshold", "min_agreement", "vehicle_crop_margin")
    @classmethod
    def _validate_thresholds(cls, value: float, info: ValidationInfo) -> float:
        """Exige umbrales en [0, 1]."""
        return _unit_interval(value, _field_name(info))

    @field_validator("dedup_window_ms")
    @classmethod
    def _validate_dedup_window_ms(cls, value: int) -> int:
        """Exige una ventana de duplicados en [0, 600000] ms."""
        if not 0 <= value <= DEDUP_WINDOW_MS_MAX:
            raise ValueError(f"dedup_window_ms debe estar en [0, 600000]: {value}")
        return value

    @field_validator("min_sharpness")
    @classmethod
    def _validate_min_sharpness(cls, value: float) -> float:
        """Exige una nitidez mínima no negativa."""
        if value < 0.0:
            raise ValueError(f"min_sharpness debe ser >= 0: {value}")
        return value

    @field_validator("near_min_width_frac")
    @classmethod
    def _validate_near_min_width_frac(cls, value: float) -> float:
        """Exige una fracción en [0, 0.2]."""
        if not 0.0 <= value <= NEAR_MIN_WIDTH_FRAC_MAX:
            raise ValueError(f"near_min_width_frac debe estar en [0, 0.2]: {value}")
        return value

    @field_validator("max_plate_vehicle_ratio")
    @classmethod
    def _validate_max_plate_vehicle_ratio(cls, value: float) -> float:
        """Exige un ratio en (0, 1]."""
        if not 0.0 < value <= 1.0:
            raise ValueError(f"max_plate_vehicle_ratio debe estar en (0, 1]: {value}")
        return value

    @field_validator("roi")
    @classmethod
    def _validate_roi(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Valida la región de interés."""
        if not (0.0 <= value[0] < value[2] <= 1.0 and 0.0 <= value[1] < value[3] <= 1.0):
            raise ValueError("roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1")
        return value


class ConsolidationConfig(StrictModel):
    """Umbral global de ambigüedad y mapa de confusiones (ADR-007)."""

    ambiguity_margin: float
    confusions: tuple[tuple[str, str], ...]

    @field_validator("ambiguity_margin")
    @classmethod
    def _validate_ambiguity_margin(cls, value: float) -> float:
        """Exige un margen en [0, 1]."""
        return _unit_interval(value, "ambiguity_margin")


class RetentionConfig(StrictModel):
    """Días de retención de recortes, registros y exportaciones de entrenamiento."""

    crops_days: int
    records_days: int
    training_days: int


class LoggingConfig(StrictModel):
    """Nivel de logging de la aplicación."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class PlateFormatConfig(StrictModel):
    """Entrada del catálogo de formatos tal como aparece en el YAML."""

    format_id: str
    category: str
    pattern: str
    regex: str
    verified: bool
    vehicle_types: tuple[VehicleType, ...]
    source: str


class AppConfig(StrictModel):
    """Configuración completa de la aplicación."""

    version: Literal[1]
    root_dir: Path
    paths: PathsConfig
    input: InputConfig
    inference: InferenceConfig
    models: ModelsConfig
    tracker: TrackerConfig
    default_profile: str
    profiles: dict[str, ProfileConfig]
    consolidation: ConsolidationConfig
    retention: RetentionConfig
    logging: LoggingConfig
    plate_formats: tuple[PlateFormatConfig, ...]

    @field_validator("profiles")
    @classmethod
    def _validate_profiles(cls, value: dict[str, ProfileConfig]) -> dict[str, ProfileConfig]:
        """Exige al menos un perfil y nombres que cumplan `^[a-z_]{1,32}$`."""
        if not value:
            raise ValueError("se requiere al menos un perfil")
        for name in value:
            if PROFILE_NAME_REGEX.fullmatch(name) is None:
                raise ValueError(f"nombre de perfil inválido: {name!r}")
        return value

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> AppConfig:
        """Comprueba el perfil por defecto, la retención y los objetos de dominio."""
        if self.default_profile not in self.profiles:
            raise ValueError(f"default_profile desconocido: {self.default_profile}")
        for profile_name, profile_config in self.profiles.items():
            if profile_config.mode == "movil" and not profile_config.camera_motion_compensation:
                raise ValueError(
                    f"el perfil {profile_name} es movil y exige camera_motion_compensation: true"
                )
        if not 1 <= self.retention.crops_days <= self.retention.records_days <= RETENTION_MAX_DAYS:
            raise ValueError(
                "retención inválida: se espera 1 <= crops_days <= records_days <= 3650"
            )
        if not 1 <= self.retention.training_days <= RETENTION_MAX_DAYS:
            raise ValueError(
                "retención de entrenamiento inválida: se espera 1 <= training_days <= 3650"
            )
        try:
            self.plate_catalog()
            self.confusion_map()
        except DomainError as error:
            raise ValueError(str(error)) from error
        return self

    def under_root(self, relative: Path) -> Path:
        """Devuelve `relative` resuelta contra la raíz del proyecto."""
        return self.root_dir / relative

    def profile(self, name: str | None) -> tuple[str, ProfileConfig]:
        """Devuelve el perfil pedido o el de por defecto.

        Raises:
            ConfigurationError: Si `name` no existe en `profiles`.
        """
        selected = self.default_profile if name is None else name
        try:
            return selected, self.profiles[selected]
        except KeyError as error:
            raise ConfigurationError(f"perfil desconocido: {selected}") from error

    def plate_catalog(self) -> PlateFormatCatalog:
        """Construye el catálogo de formatos del dominio en el orden del YAML."""
        formats = [
            PlateFormat(
                entry.format_id,
                entry.category,
                entry.pattern,
                entry.regex,
                entry.verified,
                frozenset(entry.vehicle_types),
                entry.source,
            )
            for entry in self.plate_formats
        ]
        return PlateFormatCatalog(formats)

    def confusion_map(self) -> ConfusionMap:
        """Construye el mapa de confusiones del dominio."""
        return ConfusionMap(self.consolidation.confusions)

    def consolidation_policy(self, profile: ProfileConfig) -> ConsolidationPolicy:
        """Construye la política de consolidación de un perfil."""
        return ConsolidationPolicy(
            profile.min_readings,
            profile.confirm_threshold,
            profile.min_agreement,
            self.consolidation.ambiguity_margin,
        )


def load_config(path: Path) -> AppConfig:
    """Lee y valida la configuración desde `path`.

    Args:
        path: Ruta del YAML de configuración.

    Returns:
        Configuración validada, con `root_dir` fijado al padre de `config/`.

    Raises:
        ConfigurationError: Si el archivo no se puede leer, el YAML es inválido o
            la configuración no valida.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"no se pudo leer la configuración: {path.name}") from error
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"YAML inválido: {path.name}") from error
    if not isinstance(data, dict):
        raise ConfigurationError(f"la configuración debe ser un mapeo: {path.name}")
    if "root_dir" in data:
        raise ConfigurationError("root_dir no se configura en el archivo")
    data["root_dir"] = path.resolve().parent.parent
    try:
        return AppConfig.model_validate(data)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
        )
        raise ConfigurationError(f"configuración inválida: {detail}") from error
