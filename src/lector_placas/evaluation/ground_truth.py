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

    version: Literal[1]
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    subset: Literal["street_day", "street_night", "parking", "fast"]
    camera: Literal["fixed", "handheld"]
    plates: tuple[GroundTruthPlate, ...]


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
