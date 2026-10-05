"""Registro de modelos verificado por SHA-256 contra `config/models.yaml` (ADR-012, SEG-17)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from lector_placas.domain.errors import ConfigurationError, ModelIntegrityError
from lector_placas.infrastructure.input_validation import sha256_file
from lector_placas.infrastructure.paths import resolve_within

MODEL_ID_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9-]{1,63}$"
SHA256_PATTERN: Final[str] = r"^[0-9a-f]{64}$"
ALLOWED_PREFIX: Final[str] = "https://github.com/"
PENDING_EXPORT: Final[str] = "PENDIENTE_EXPORT"
FORBIDDEN_FILENAME_PARTS: Final[tuple[str, ...]] = ("/", "\\", "..")


class ModelEntry(BaseModel):
    """Entrada del manifiesto que describe un modelo, su origen y su integridad.

    Precondiciones:
        `model_id` cumple `^[a-z0-9][a-z0-9-]{1,63}$`; `filename` no está vacío y no contiene
        `/`, barra invertida ni `..`; `url` es `None` o empieza por `https://github.com/`;
        `sha256` es hexadecimal de 64 caracteres o `PENDIENTE_EXPORT`; `size_bytes >= 0`.

    Postcondiciones:
        Instancia inmutable con los campos validados.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(pattern=MODEL_ID_PATTERN)
    filename: str = Field(min_length=1)
    url: str | None
    sha256: str
    size_bytes: int = Field(ge=0)
    license: str
    source: str

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if any(part in value for part in FORBIDDEN_FILENAME_PARTS):
            raise ValueError(f"filename no admite '/', '\\' ni '..': {value}")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(ALLOWED_PREFIX):
            raise ValueError(f"url debe empezar por {ALLOWED_PREFIX}: {value}")
        return value

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if value != PENDING_EXPORT and re.fullmatch(SHA256_PATTERN, value) is None:
            raise ValueError(f"sha256 no es hexadecimal de 64 caracteres: {value}")
        return value


class ModelManifest(BaseModel):
    """Manifiesto versionado con las entradas de modelos, sin `model_id` repetidos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    models: tuple[ModelEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> Self:
        identifiers = [entry.model_id for entry in self.models]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("model_id duplicado en el manifiesto")
        return self

    def entry(self, model_id: str) -> ModelEntry:
        """Devuelve la entrada del modelo `model_id`.

        Args:
            model_id: Identificador del modelo buscado.

        Returns:
            La entrada correspondiente del manifiesto.

        Raises:
            ModelIntegrityError: Si el manifiesto no declara ese `model_id`.
        """
        for entry in self.models:
            if entry.model_id == model_id:
                return entry
        raise ModelIntegrityError(f"modelo desconocido: {model_id}")


def load_manifest(path: Path) -> ModelManifest:
    """Lee y valida el manifiesto de modelos desde `path`.

    Args:
        path: Ruta del YAML del manifiesto.

    Returns:
        Manifiesto validado.

    Raises:
        ConfigurationError: Si el archivo no se puede leer, el YAML es inválido o el
            contenido no valida contra el esquema.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(_invalid(f"no se pudo leer {path.name}")) from error
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ConfigurationError(_invalid(f"YAML no válido en {path.name}")) from error
    if not isinstance(data, dict):
        raise ConfigurationError(_invalid(f"se esperaba un mapeo en {path.name}"))
    try:
        return ModelManifest.model_validate(data)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
        )
        raise ConfigurationError(_invalid(detail)) from error


def _invalid(detail: str) -> str:
    """Compone el mensaje de error del manifiesto con su detalle."""
    return f"manifiesto de modelos inválido: {detail}"


class ManifestModelRegistry:
    """Registro de modelos respaldado por un manifiesto verificado por SHA-256."""

    def __init__(self, manifest_path: Path, models_dir: Path) -> None:
        """Carga el manifiesto y recuerda el directorio raíz de los modelos.

        Args:
            manifest_path: Ruta del manifiesto (`config/models.yaml`).
            models_dir: Directorio que contiene `models/<model_id>/<filename>`.

        Raises:
            ConfigurationError: Si el manifiesto no se puede leer o no valida.
        """
        self._manifest = load_manifest(manifest_path)
        self._models_dir = models_dir

    def verified_path(self, model_id: str) -> Path:
        """Devuelve la ruta del modelo tras verificar su SHA-256.

        Args:
            model_id: Identificador del modelo en el manifiesto.

        Returns:
            Ruta absoluta del archivo del modelo, con el hash recalculado en esta llamada.

        Raises:
            ModelIntegrityError: Si el modelo es desconocido, aún no se ha exportado, el
                archivo no existe o su SHA-256 no coincide con el manifiesto.
            UnsafePathError: Si la ruta resuelta escapa de `models_dir`.
        """
        entry = self._manifest.entry(model_id)
        if entry.sha256 == PENDING_EXPORT:
            raise ModelIntegrityError(f"modelo no exportado: {model_id}")
        path = resolve_within(self._models_dir, Path(model_id) / entry.filename)
        if not path.is_file():
            raise ModelIntegrityError(
                f"modelo no encontrado: {model_id}; ejecute 'lector models fetch'"
            )
        if sha256_file(path) != entry.sha256:
            raise ModelIntegrityError(f"hash SHA-256 no coincide: {model_id}")
        return path
