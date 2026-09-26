"""Consulta del catálogo de formatos de placa por longitud, patrón y regex."""

from __future__ import annotations

from collections.abc import Sequence

from lector_placas.domain.entities import PLATE_TEXT_REGEX, PlateFormat
from lector_placas.domain.errors import InvalidPlateTextError, PlateFormatCatalogError


def text_pattern(text: str) -> str:
    """Devuelve la forma del texto con `L` para letras y `D` para dígitos.

    Args:
        text: Texto de placa que debe cumplir `PLATE_TEXT_REGEX`.

    Returns:
        Patrón de la misma longitud que `text`.

    Raises:
        InvalidPlateTextError: Si `text` no cumple `PLATE_TEXT_REGEX`.
    """
    if PLATE_TEXT_REGEX.fullmatch(text) is None:
        raise InvalidPlateTextError(f"texto de placa inválido (longitud={len(text)})")
    return "".join("L" if character.isalpha() else "D" for character in text)


class PlateFormatCatalog:
    """Catálogo inmutable de formatos, consultable por patrón y por coincidencia."""

    def __init__(self, formats: Sequence[PlateFormat]) -> None:
        """Guarda los formatos en el orden recibido.

        Args:
            formats: Formatos que componen el catálogo; no puede estar vacío ni repetir `format_id`.

        Raises:
            PlateFormatCatalogError: Si `formats` está vacío o hay `format_id` repetidos.
        """
        if not formats:
            raise PlateFormatCatalogError("el catálogo de formatos está vacío")
        self._formats = tuple(formats)
        self._require_unique_ids()

    def _require_unique_ids(self) -> None:
        """Exige que no haya dos formatos con el mismo `format_id`."""
        seen: set[str] = set()
        for plate_format in self._formats:
            if plate_format.format_id in seen:
                raise PlateFormatCatalogError(f"format_id repetido: {plate_format.format_id}")
            seen.add(plate_format.format_id)

    @property
    def formats(self) -> tuple[PlateFormat, ...]:
        """Formatos del catálogo en su orden original."""
        return self._formats

    def patterns_of_length(self, length: int) -> tuple[str, ...]:
        """Patrones distintos de esa longitud, ordenados alfabéticamente."""
        patterns = {fmt.pattern for fmt in self._formats if len(fmt.pattern) == length}
        return tuple(sorted(patterns))

    def matching(self, text: str) -> tuple[PlateFormat, ...]:
        """Formatos cuya expresión regular acepta `text` completo, en orden del catálogo."""
        return tuple(fmt for fmt in self._formats if fmt.matches(text))

    def matching_with_pattern(self, text: str, pattern: str) -> tuple[PlateFormat, ...]:
        """Como `matching`, restringido además a los formatos con ese patrón."""
        return tuple(fmt for fmt in self._formats if fmt.pattern == pattern and fmt.matches(text))
