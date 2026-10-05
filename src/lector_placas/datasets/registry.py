"""Registro de los datasets públicos que descarga `lector dataset download`.

El registro (`config/datasets.yaml`) declara, por dataset, su proyecto de Roboflow, su
destino (detector u OCR), las clases que contienen placas y su licencia. De aquí salen
tanto las descargas como el manifiesto `sources.yaml` que consume `merge-detection`.
"""

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

from lector_placas.datasets.yolo_format import read_class_names
from lector_placas.domain.errors import DatasetError

AUTO: Final[str] = "auto"
NAME_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_-]{1,40}$")
SLUG_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_-]{1,100}$")


class DatasetEntry(BaseModel):
    """Dataset público a descargar, con su proyecto de Roboflow y su licencia."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    workspace: str
    project: str
    target: Literal["detector", "ocr"]
    plate_classes: str | tuple[str, ...] = AUTO
    license: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Exige nombres de dataset que cumplan `NAME_REGEX`."""
        if NAME_REGEX.fullmatch(value) is None:
            raise ValueError(f"nombre de dataset inválido: {value!r}")
        return value

    @field_validator("workspace", "project")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        """Exige identificadores de Roboflow que cumplan `SLUG_REGEX`."""
        if SLUG_REGEX.fullmatch(value) is None:
            raise ValueError(f"identificador de Roboflow inválido: {value!r}")
        return value

    @field_validator("plate_classes")
    @classmethod
    def _validate_plate_classes(cls, value: str | tuple[str, ...]) -> str | tuple[str, ...]:
        """Admite solo `auto` o una lista de clases no vacía."""
        if value == AUTO:
            return value
        if isinstance(value, str) or not value:
            raise ValueError("plate_classes debe ser 'auto' o una lista no vacía")
        return value

    @field_validator("license")
    @classmethod
    def _validate_license(cls, value: str) -> str:
        """Exige una licencia declarada no vacía."""
        if not value.strip():
            raise ValueError("la licencia no puede estar vacía")
        return value


class DatasetRegistry(BaseModel):
    """Registro versionado de datasets y del formato de exportación que usan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    format: Literal["yolov8"]
    datasets: tuple[DatasetEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_duplicate_names(self) -> DatasetRegistry:
        """Exige que los nombres de dataset sean únicos."""
        names = [entry.name for entry in self.datasets]
        if len(set(names)) != len(names):
            raise ValueError("nombres de dataset repetidos")
        return self


def load_registry(path: Path) -> DatasetRegistry:
    """Lee y valida el registro de datasets.

    Args:
        path: Ruta del YAML del registro.

    Returns:
        El registro validado.

    Raises:
        DatasetError: Si el archivo no se puede leer, el YAML es inválido o el
            registro no valida.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"registro de datasets inválido: {path.name}") from error
    try:
        return DatasetRegistry.model_validate(data)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
        )
        raise DatasetError(f"registro de datasets inválido: {detail}") from error


def resolve_plate_classes(entry: DatasetEntry, dataset_dir: Path) -> tuple[str, ...]:
    """Resuelve las clases que contienen placas de un dataset descargado.

    Args:
        entry: Entrada del registro con `plate_classes` explícitas o `auto`.
        dataset_dir: Directorio del dataset descargado, con su `data.yaml`.

    Returns:
        Las clases de placa declaradas o, con `auto`, la única clase del dataset.

    Raises:
        DatasetError: Si `auto` no encuentra exactamente una clase o si el
            `data.yaml` no se puede leer.
    """
    if isinstance(entry.plate_classes, tuple):
        return entry.plate_classes
    names = read_class_names(dataset_dir / "data.yaml")
    if len(names) != 1:
        found = ", ".join(names.values())
        raise DatasetError(
            f"{entry.name}: plate_classes=auto exige una sola clase; encontradas: {found}"
        )
    return (next(iter(names.values())),)


def write_sources_file(registry: DatasetRegistry, raw_root: Path, path: Path) -> int:
    """Escribe el manifiesto de fuentes de los datasets de detección ya descargados.

    Args:
        registry: Registro con todos los datasets declarados.
        raw_root: Directorio de descargas del detector, con una carpeta por dataset.
        path: Ruta del YAML de fuentes a escribir.

    Returns:
        Cuántas fuentes se escribieron.

    Raises:
        DatasetError: Si no hay ningún dataset de detección descargado o si las
            clases de placa no se pueden resolver.
    """
    sources = [
        _source_of(entry, raw_root / entry.name)
        for entry in _downloaded_detectors(registry, raw_root)
    ]
    if not sources:
        raise DatasetError("no hay datasets de detección descargados")
    text = yaml.safe_dump({"version": 1, "sources": sources}, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    return len(sources)


def _downloaded_detectors(registry: DatasetRegistry, raw_root: Path) -> tuple[DatasetEntry, ...]:
    """Devuelve las entradas de detección cuya carpeta de descarga ya existe."""
    return tuple(
        entry
        for entry in registry.datasets
        if entry.target == "detector" and (raw_root / entry.name).is_dir()
    )


def _source_of(entry: DatasetEntry, directory: Path) -> dict[str, object]:
    """Construye la fuente del manifiesto para un dataset ya descargado."""
    return {
        "name": entry.name,
        "path": entry.name,
        "url": f"https://universe.roboflow.com/{entry.workspace}/{entry.project}",
        "license": entry.license,
        "plate_classes": list(resolve_plate_classes(entry, directory)),
    }
