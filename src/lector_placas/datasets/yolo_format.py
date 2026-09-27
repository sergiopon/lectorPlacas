"""Lectura y escritura de etiquetas en el formato YOLO (docs/04-evaluacion.md §5.4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from lector_placas.domain.entities import BoundingBox
from lector_placas.domain.errors import DatasetError

FIELD_COUNT: Final[int] = 5
POLYGON_MIN_POINTS: Final[int] = 3
POLYGON_MIN_FIELDS: Final[int] = 1 + 2 * POLYGON_MIN_POINTS


@dataclass(frozen=True, slots=True)
class YoloBox:
    """Caja YOLO normalizada respecto al ancho y alto de la imagen."""

    class_id: int
    cx: float
    cy: float
    w: float
    h: float

    def __post_init__(self) -> None:
        """Valida el rango del identificador de clase y de las coordenadas normalizadas.

        Raises:
            DatasetError: si la clase es negativa, el centro sale de [0, 1] o `w`/`h`
                sale de (0, 1].
        """
        if self.class_id < 0 or not 0.0 <= self.cx <= 1.0 or not 0.0 <= self.cy <= 1.0:
            raise DatasetError("caja YOLO fuera de rango")
        if not 0.0 < self.w <= 1.0 or not 0.0 < self.h <= 1.0:
            raise DatasetError("caja YOLO fuera de rango")


def parse_label_file(path: Path) -> list[YoloBox]:
    """Lee las cajas de un archivo de etiquetas YOLO.

    Args:
        path: ruta del archivo de etiquetas.

    Returns:
        Las cajas en el orden del archivo; lista vacía si el archivo no existe o
        no tiene líneas no vacías.

    Raises:
        DatasetError: si una línea no es una caja de 5 campos válida ni un polígono
            válido de al menos 3 puntos.
    """
    if not path.exists():
        return []
    boxes: list[YoloBox] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            boxes.append(_parse_line(line.split(), path.name, number))
    return boxes


def format_labels(boxes: Sequence[YoloBox]) -> str:
    """Serializa las cajas como líneas `clase cx cy w h` con 6 decimales.

    Args:
        boxes: cajas a serializar.

    Returns:
        Una línea por caja terminada en un salto de línea, o `""` si no hay cajas.
    """
    return "".join(
        f"{box.class_id} {box.cx:.6f} {box.cy:.6f} {box.w:.6f} {box.h:.6f}\n" for box in boxes
    )


def yolo_to_pixels(box: YoloBox, width: int, height: int) -> BoundingBox | None:
    """Convierte una caja normalizada a píxeles, recortándola a la imagen.

    Args:
        box: caja normalizada.
        width: ancho de la imagen en píxeles.
        height: alto de la imagen en píxeles.

    Returns:
        La caja en píxeles, o `None` si el resultado queda vacío.
    """
    if width <= 0 or height <= 0:
        return None
    x1 = max(0.0, (box.cx - box.w / 2) * width)
    y1 = max(0.0, (box.cy - box.h / 2) * height)
    x2 = min(float(width), (box.cx + box.w / 2) * width)
    y2 = min(float(height), (box.cy + box.h / 2) * height)
    if x2 <= x1 or y2 <= y1:
        return None
    return BoundingBox(x1, y1, x2, y2)


def read_class_names(data_yaml: Path) -> dict[int, str]:
    """Lee el mapa id→nombre de clases del `data.yaml` de un dataset YOLO.

    Args:
        data_yaml: ruta del `data.yaml`.

    Returns:
        Mapa de identificador de clase a nombre.

    Raises:
        DatasetError: si el archivo no se puede leer, no es YAML válido o `names`
            no es una lista ni un mapa de claves enteras.
    """
    try:
        data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"data.yaml inválido: {data_yaml.name}") from error
    names = data.get("names") if isinstance(data, dict) else None
    if isinstance(names, list):
        return {index: str(name) for index, name in enumerate(names)}
    if isinstance(names, dict):
        try:
            return {int(key): str(value) for key, value in names.items()}
        except (TypeError, ValueError) as error:
            raise DatasetError(f"data.yaml inválido: {data_yaml.name}") from error
    raise DatasetError(f"data.yaml inválido: {data_yaml.name}")


def _parse_line(fields: list[str], name: str, number: int) -> YoloBox:
    """Convierte los campos de una línea de etiqueta en una caja YOLO.

    Una línea de 5 campos es una caja; una con un número impar de campos y al menos
    `POLYGON_MIN_FIELDS` es un polígono, que se reduce a su caja envolvente.

    Raises:
        DatasetError: si la forma no es una caja ni un polígono, los campos no son
            numéricos o el resultado sale de los rangos de `YoloBox`.
    """
    if len(fields) != FIELD_COUNT and not _is_polygon(fields):
        raise DatasetError(f"etiqueta inválida: {name}:{number}")
    try:
        if len(fields) == FIELD_COUNT:
            return _parse_box(fields)
        return _parse_polygon(fields)
    except (ValueError, DatasetError) as error:
        raise DatasetError(f"etiqueta inválida: {name}:{number}") from error


def _is_polygon(fields: list[str]) -> bool:
    """Indica si los campos tienen la forma `clase x1 y1 ... xn yn` con n >= 3."""
    return len(fields) >= POLYGON_MIN_FIELDS and len(fields) % 2 == 1


def _parse_box(fields: list[str]) -> YoloBox:
    """Convierte los 5 campos `clase cx cy w h` de una caja."""
    return YoloBox(
        int(fields[0]),
        float(fields[1]),
        float(fields[2]),
        float(fields[3]),
        float(fields[4]),
    )


def _parse_polygon(fields: list[str]) -> YoloBox:
    """Convierte el polígono `clase x1 y1 ... xn yn` en su caja envolvente."""
    coords = [float(field) for field in fields[1:]]
    xs, ys = coords[0::2], coords[1::2]
    return YoloBox(
        int(fields[0]),
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        max(xs) - min(xs),
        max(ys) - min(ys),
    )
