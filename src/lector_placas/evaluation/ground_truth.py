"""Ground truth de evaluación: formato JSON por video (docs/04-evaluacion.md §2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from lector_placas.domain.entities import PLATE_TEXT_REGEX, VehicleType
from lector_placas.domain.errors import EvaluationError

INVALID_MESSAGE: str = "ground truth inválido"


class GroundTruthPlate(BaseModel):
    """Placa anotada a mano en el ground truth de un video."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    vehicle_type: VehicleType
    first_seen_ms: int = Field(ge=0)
    last_seen_ms: int
    legible: bool
    max_plate_width_px: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_plate(self) -> GroundTruthPlate:
        """Exige texto válido si es legible, vacío si no, y el orden de los tiempos."""
        if self.legible:
            if PLATE_TEXT_REGEX.fullmatch(self.text) is None:
                raise ValueError("una placa legible debe tener un texto válido")
        elif self.text != "":
            raise ValueError("una placa no legible debe tener texto vacío")
        if self.last_seen_ms < self.first_seen_ms:
            raise ValueError("last_seen_ms debe ser >= first_seen_ms")
        return self


class GroundTruth(BaseModel):
    """Anotación completa de un video de evaluación."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1, 2]
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    subset: Literal["street_day", "street_night", "parking", "fast", "patrol"]
    camera: Literal["fixed", "handheld", "vehicle_mounted"]
    plates: tuple[GroundTruthPlate, ...]

    @model_validator(mode="after")
    def _validate_version(self) -> GroundTruth:
        """Exige los campos y modos propios de cada versión del ground truth."""
        if self.version == 1:
            if any(plate.max_plate_width_px is not None for plate in self.plates):
                raise ValueError("max_plate_width_px solo existe en la versión 2")
            if self.subset == "patrol" or self.camera == "vehicle_mounted":
                raise ValueError("patrol y vehicle_mounted exigen la versión 2")
        elif any(plate.legible and plate.max_plate_width_px is None for plate in self.plates):
            raise ValueError("versión 2: falta max_plate_width_px en una placa legible")
        return self


def load_ground_truth(path: Path) -> GroundTruth:
    """Carga y valida el ground truth de un video.

    Args:
        path: ruta del JSON de anotación.

    Returns:
        El ground truth validado.

    Raises:
        EvaluationError: si el archivo no se puede leer, no es JSON válido o no
            cumple el esquema; el mensaje no incluye el contenido del archivo.
    """
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"{INVALID_MESSAGE}: {path.name}") from error
    try:
        return GroundTruth.model_validate(data)
    except ValidationError as error:
        raise EvaluationError(f"{INVALID_MESSAGE}: {path.name}") from error
