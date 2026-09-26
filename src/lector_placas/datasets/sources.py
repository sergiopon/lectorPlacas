"""Manifiesto de las fuentes de datasets descargadas manualmente desde Roboflow."""

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
    field_validator,
    model_validator,
)

from lector_placas.domain.errors import DatasetError

PLACEHOLDER: Final[str] = "COMPLETAR"
NAME_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_-]{1,40}$")


class DatasetSource(BaseModel):
    """Fuente de dataset: ubicación local, procedencia y clases que contienen placas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    path: Path
    url: str
    license: str
    plate_classes: tuple[str, ...] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Exige nombres que cumplan `NAME_REGEX`."""
        if NAME_REGEX.fullmatch(value) is None:
            raise ValueError(f"nombre de fuente inválido: {value!r}")
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: Path) -> Path:
        """Rechaza rutas absolutas o con `..`."""
        if value.is_absolute() or ".." in value.parts:
            raise ValueError(f"la ruta debe ser relativa y sin '..': {value}")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        """Exige una URL https."""
        if not value.startswith("https://"):
            raise ValueError(f"la url debe empezar por https://: {value}")
        return value

    @field_validator("license")
    @classmethod
    def _validate_license(cls, value: str) -> str:
        """Exige una licencia declarada no vacía."""
        if not value.strip():
            raise ValueError("la licencia no puede estar vacía")
        return value

    @model_validator(mode="after")
    def _reject_placeholder(self) -> DatasetSource:
        """Rechaza `plate_classes` sin completar tras revisar el `data.yaml`."""
        if PLACEHOLDER in self.plate_classes:
            raise ValueError(f"complete plate_classes de {self.name} leyendo su data.yaml")
        return self


class SourcesFile(BaseModel):
    """Manifiesto versionado con las fuentes de un dataset de detección."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    sources: tuple[DatasetSource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_duplicate_names(self) -> SourcesFile:
        """Exige que los nombres de fuente sean únicos."""
        names = [source.name for source in self.sources]
        if len(set(names)) != len(names):
            raise ValueError("nombres de fuente repetidos")
        return self


def load_sources(path: Path) -> SourcesFile:
    """Lee y valida el manifiesto de fuentes.

    Args:
        path: ruta del YAML de fuentes.

    Returns:
        El manifiesto validado.

    Raises:
        DatasetError: si el archivo no se puede leer, el YAML es inválido o el
            manifiesto no valida.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"fuentes inválidas: {path.name}") from error
    try:
        return SourcesFile.model_validate(data)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
        )
        raise DatasetError(f"fuentes inválidas: {detail}") from error
