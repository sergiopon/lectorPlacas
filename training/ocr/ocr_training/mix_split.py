"""Lógica pura de agrupación, reparto y cuota de la mezcla real + sintético del OCR.

Sin entrada/salida: recibe y devuelve `Sample` en memoria. El reparto agrupa los
recortes reales por texto de placa o por imagen de origen (spec 039) para que el
mismo vehículo no quede repartido entre particiones, y la selección de sintéticos
respeta una cuota de motos sobre el `train` resultante.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from ocr_training.common import TrainingError

MOTO_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]?$")
MOTOCARRO_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9]{3}[A-Z]{3}$")
ROBOFLOW_NAME_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^(?P<source>.+?)__(?P<stem>.+)\.rf\.[0-9a-fA-F]+_(?P<index>\d+)\.png$"
)
CATEGORIES: Final[tuple[str, ...]] = ("moto", "motocarro", "other")
SPLITS: Final[tuple[str, ...]] = ("train", "val", "test")
SYNTHETIC_MOTOCARRO_SHARE: Final[float] = 0.15

_EPSILON: Final[float] = 1e-9


@dataclass(frozen=True, slots=True)
class Sample:
    """Recorte de placa anotado, con su partición lógica.

    Args:
        image: Ruta absoluta resuelta de la imagen de origen.
        text: Texto de placa (`plate_text`).
        origin: Grupo de imagen de origen (ver `origin_group`).
        real: `False` para sintéticos.
    """

    image: Path
    text: str
    origin: str
    real: bool


def category(text: str) -> str:
    """Clasifica un texto de placa en `moto`, `motocarro` u `other`.

    Args:
        text: Texto de placa.

    Returns:
        La categoría correspondiente.
    """
    if MOTO_REGEX.fullmatch(text):
        return "moto"
    if MOTOCARRO_REGEX.fullmatch(text):
        return "motocarro"
    return "other"


def origin_group(source_name: str, relative_path: str) -> str:
    """Calcula el grupo de imagen de origen de un recorte.

    Las copias renombradas por Roboflow (`.rf.<hash>`) y todos los recortes de la
    misma imagen comparten grupo.

    Args:
        source_name: Nombre del directorio del dataset de origen.
        relative_path: Ruta del recorte relativa al dataset de origen, en POSIX.

    Returns:
        El identificador del grupo de origen.
    """
    name = PurePosixPath(relative_path).name
    match = ROBOFLOW_NAME_REGEX.fullmatch(name)
    if match is None:
        return f"{source_name}/{relative_path}"
    return f"{source_name}/{match['source']}/{match['stem']}"


def components(samples: Sequence[Sample]) -> list[list[Sample]]:
    """Agrupa muestras que comparten texto de placa o imagen de origen.

    Args:
        samples: Muestras en orden de entrada.

    Returns:
        Componentes ordenados por el menor índice de sus muestras, con las
        muestras de cada componente en orden de índice creciente.
    """
    parent = list(range(len(samples)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    seen_text: dict[str, int] = {}
    seen_origin: dict[str, int] = {}
    for index, sample in enumerate(samples):
        for key, table in ((sample.text, seen_text), (sample.origin, seen_origin)):
            earlier = table.get(key)
            if earlier is None:
                table[key] = index
            else:
                union(index, earlier)
    grouped: dict[int, list[Sample]] = {}
    for index, sample in enumerate(samples):
        grouped.setdefault(find(index), []).append(sample)
    return [grouped[root] for root in sorted(grouped)]


def component_category(component: Sequence[Sample]) -> str:
    """Determina la categoría de un componente por prioridad moto > motocarro > other.

    Args:
        component: Muestras del componente.

    Returns:
        La categoría del componente.
    """
    present = {category(sample.text) for sample in component}
    for name in CATEGORIES:
        if name in present:
            return name
    return "other"


def split_components(
    comps: Sequence[Sequence[Sample]], val_fraction: float, test_fraction: float, seed: int
) -> dict[str, list[list[Sample]]]:
    """Reparte los componentes en train/val/test de forma estratificada por categoría.

    Args:
        comps: Componentes de la muestra real.
        val_fraction: Fracción de componentes de cada categoría asignada a `val`.
        test_fraction: Fracción de componentes de cada categoría asignada a `test`.
        seed: Semilla del orden determinista por hash.

    Returns:
        Diccionario con las claves `train`, `val` y `test`.

    Raises:
        TrainingError: si las fracciones no cumplen `val > 0`, `test > 0` y
            `val + test < 1`, o si alguna partición queda vacía.
    """
    if val_fraction <= 0 or test_fraction <= 0 or val_fraction + test_fraction >= 1:
        raise TrainingError(
            f"fracciones inválidas: val={val_fraction} test={test_fraction}"
        )
    parts: dict[str, list[list[Sample]]] = {split: [] for split in SPLITS}
    for name in CATEGORIES:
        group = [comp for comp in comps if component_category(comp) == name]
        group.sort(key=_component_key(seed))
        count = len(group)
        n_test = math.floor(count * test_fraction + 0.5)
        n_val = math.floor(count * val_fraction + 0.5)
        parts["test"].extend(list(comp) for comp in group[:n_test])
        parts["val"].extend(list(comp) for comp in group[n_test : n_test + n_val])
        parts["train"].extend(list(comp) for comp in group[n_test + n_val :])
    for split in SPLITS:
        if not parts[split]:
            raise TrainingError(f"partición vacía: {split}")
    return parts


def _component_key(seed: int) -> Callable[[Sequence[Sample]], str]:
    """Devuelve la clave de orden determinista de un componente por su origen mínimo."""

    def key(component: Sequence[Sample]) -> str:
        origin = min(sample.origin for sample in component)
        return hashlib.sha256(f"{seed}\n{origin}".encode("utf-8")).hexdigest()

    return key


def select_synthetic(
    synthetic: Sequence[Sample],
    real_train: Sequence[Sample],
    excluded_texts: Set[str],
    ratio: float,
    min_moto_fraction: float,
    seed: int,
) -> list[Sample]:
    """Selecciona los sintéticos que se añaden a `train` con cuota de motos.

    Args:
        synthetic: Sintéticos disponibles, en orden de entrada.
        real_train: Muestras reales asignadas a `train`.
        excluded_texts: Textos reales de `val`/`test`; se descartan los sintéticos
            que coincidan con ellos.
        ratio: Proporción de sintéticos respecto al `train` real (`synthetic <= 50 %`).
        min_moto_fraction: Fracción mínima de motos en el `train` final.
        seed: Semilla del orden aleatorio determinista.

    Returns:
        La selección en el orden moto, motocarro, other.

    Raises:
        TrainingError: si `ratio` o `min_moto_fraction` están fuera de rango, o si
            faltan sintéticos de alguna categoría para cubrir la cuota.
    """
    if not 0.0 <= ratio <= 1.0 or not 0.0 <= min_moto_fraction < 1.0:
        raise TrainingError(
            f"parámetros inválidos: ratio={ratio} min_moto_fraction={min_moto_fraction}"
        )
    target = math.floor(len(real_train) * ratio)
    if target == 0:
        return []
    real_moto = sum(1 for sample in real_train if category(sample.text) == "moto")
    needed = max(
        0,
        math.ceil(min_moto_fraction * (len(real_train) + target) - _EPSILON) - real_moto,
    )
    quotas = {"moto": min(needed, target)}
    quotas["motocarro"] = math.floor((target - quotas["moto"]) * SYNTHETIC_MOTOCARRO_SHARE + 0.5)
    quotas["other"] = target - quotas["moto"] - quotas["motocarro"]
    pools: dict[str, list[Sample]] = {name: [] for name in CATEGORIES}
    for sample in synthetic:
        if sample.text not in excluded_texts:
            pools[category(sample.text)].append(sample)
    rng = random.Random(seed)
    chosen: list[Sample] = []
    for name in CATEGORIES:
        pool = list(pools[name])
        rng.shuffle(pool)
        if len(pool) < quotas[name]:
            raise TrainingError(
                f"faltan sintéticos de {name}: se necesitan {quotas[name]}, hay {len(pool)}"
            )
        chosen.extend(pool[: quotas[name]])
    return chosen
