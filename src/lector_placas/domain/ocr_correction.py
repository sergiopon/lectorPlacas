"""Corrección posicional de confusiones del OCR según un patrón `L`/`D`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from lector_placas.domain.entities import PATTERN_REGEX, PLATE_TEXT_REGEX
from lector_placas.domain.errors import (
    InvalidEntityError,
    InvalidPlateTextError,
    PlateFormatCatalogError,
)

LETTER_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]$")
DIGIT_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9]$")
PAIR_LENGTH: Final[int] = 2


@dataclass(frozen=True, slots=True)
class ConfusionMap:
    """Pares (letra, dígito) que el OCR puede confundir."""

    pairs: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Valida que cada par sea letra/dígito, sin letras ni dígitos repetidos."""
        letters: set[str] = set()
        digits: set[str] = set()
        for pair in self.pairs:
            _require_pair(pair)
            letter, digit = pair
            if letter in letters:
                raise InvalidEntityError(f"mapa de confusiones inválido: letra repetida {letter}")
            if digit in digits:
                raise InvalidEntityError(f"mapa de confusiones inválido: dígito repetido {digit}")
            letters.add(letter)
            digits.add(digit)

    @classmethod
    def default(cls) -> ConfusionMap:
        """Mapa por defecto: O↔0, I↔1, B↔8 y S↔5."""
        return cls((("O", "0"), ("I", "1"), ("B", "8"), ("S", "5")))

    def to_digit(self, char: str) -> str:
        """Devuelve el dígito del par cuya letra sea `char`, o `char` sin cambios."""
        for letter, digit in self.pairs:
            if char == letter:
                return digit
        return char

    def to_letter(self, char: str) -> str:
        """Devuelve la letra del par cuyo dígito sea `char`, o `char` sin cambios."""
        for letter, digit in self.pairs:
            if char == digit:
                return letter
        return char


def correct_to_pattern(text: str, pattern: str, confusions: ConfusionMap) -> str:
    """Ajusta `text` al patrón `L`/`D` sustituyendo los caracteres confundibles."""
    _require_plate_text(text)
    _require_pattern(pattern)
    if len(text) != len(pattern):
        raise InvalidPlateTextError("longitud de texto y patrón distintas")
    return "".join(
        _correct_char(char, kind, confusions) for char, kind in zip(text, pattern, strict=True)
    )


def _correct_char(char: str, kind: str, confusions: ConfusionMap) -> str:
    """Corrige un carácter según el tipo que exige su posición del patrón."""
    if kind == "D" and char.isalpha():
        return confusions.to_digit(char)
    if kind == "L" and char.isdigit():
        return confusions.to_letter(char)
    return char


def _require_pair(pair: tuple[str, str]) -> None:
    """Exige un par de dos elementos formado por una letra y un dígito."""
    if (
        len(pair) != PAIR_LENGTH
        or LETTER_REGEX.fullmatch(pair[0]) is None
        or DIGIT_REGEX.fullmatch(pair[1]) is None
    ):
        raise InvalidEntityError("mapa de confusiones inválido: se espera (letra, dígito)")


def _require_plate_text(text: str) -> None:
    """Exige que el texto cumpla PLATE_TEXT_REGEX sin exponer su contenido."""
    if PLATE_TEXT_REGEX.fullmatch(text) is None:
        raise InvalidPlateTextError(f"texto de placa inválido (longitud={len(text)})")


def _require_pattern(pattern: str) -> None:
    """Exige que el patrón cumpla PATTERN_REGEX sin exponer el texto de la placa."""
    if PATTERN_REGEX.fullmatch(pattern) is None:
        raise PlateFormatCatalogError(f"patrón inválido (longitud={len(pattern)})")
