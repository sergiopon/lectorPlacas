"""M-04: distancia de edición y tasas de error de carácter (docs/04-evaluacion.md §3)."""

from __future__ import annotations

from collections.abc import Sequence

from lector_placas.domain.errors import EvaluationError

EMPTY_MESSAGE: str = "se requiere al menos un par (predicción, verdad)"


def levenshtein(a: str, b: str) -> int:
    """Calcula la distancia de edición entre dos cadenas.

    Args:
        a: primera cadena.
        b: segunda cadena.

    Returns:
        El mínimo número de inserciones, borrados y sustituciones (costo 1 cada uno).
    """
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for index_a, char_a in enumerate(a, start=1):
        current = [index_a]
        for index_b, char_b in enumerate(b, start=1):
            substitution = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[index_b] + 1,
                    current[index_b - 1] + 1,
                    previous[index_b - 1] + substitution,
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(pairs: Sequence[tuple[str, str]]) -> float:
    """Calcula el CER sobre pares (predicción, verdad).

    Args:
        pairs: pares de texto; el segundo elemento es la verdad.

    Returns:
        La suma de distancias de edición dividida entre la suma de longitudes de la verdad.

    Raises:
        EvaluationError: si no hay pares o la suma de longitudes de la verdad es cero.
    """
    total_length = sum(len(truth) for _, truth in pairs)
    if not pairs or total_length == 0:
        raise EvaluationError(EMPTY_MESSAGE)
    return sum(levenshtein(prediction, truth) for prediction, truth in pairs) / total_length


def exact_match_rate(pairs: Sequence[tuple[str, str]]) -> float:
    """Calcula la fracción de pares (predicción, verdad) con coincidencia exacta.

    Args:
        pairs: pares de texto; el segundo elemento es la verdad.

    Returns:
        La fracción de pares que coinciden exactamente.

    Raises:
        EvaluationError: si no hay pares.
    """
    if not pairs:
        raise EvaluationError(EMPTY_MESSAGE)
    return sum(1 for prediction, truth in pairs if prediction == truth) / len(pairs)
