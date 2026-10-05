"""Generador de recortes sintéticos de placas colombianas para el OCR.

Genera recortes (carro amarillo/blanco, moto y motocarro) con su texto en el
formato CSV de fast-plate-ocr, para complementar el fine-tuning del OCR.

Las medidas de la placa son aproximadas (tipografía oficial,
alto de caracteres de la placa de carro estándar y colores RGB exactos) y se
tratan aquí como aproximaciones visuales, no como valores oficiales.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

from ocr_training.common import DATASETS_DIR, TrainingError

DEFAULT_FONT: Final[Path] = Path("/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf")
LETTERS: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS: Final[str] = "0123456789"
YELLOW_BGR: Final[tuple[int, int, int]] = (0, 200, 255)  # aproximación visual, no valor oficial
WHITE_BGR: Final[tuple[int, int, int]] = (245, 245, 245)  # aproximación visual
MUNICIPALITIES: Final[tuple[str, ...]] = (
    "BOGOTA D.C.",
    "MEDELLIN",
    "CALI",
    "BARRANQUILLA",
    "BUCARAMANGA",
)

_INK_RGB: Final[tuple[int, int, int]] = (0, 0, 0)
_BORDER_MM: Final[float] = 2.0
_MAIN_WIDTH_RATIO: Final[float] = 0.9
_BOTTOM_WIDTH_RATIO: Final[float] = 0.8
_MIN_PX_PER_MM: Final[float] = 0.25
_MAX_PX_PER_MM: Final[float] = 0.6
_ROTATION_DEG: Final[float] = 5.0
_BLUR_PROBABILITY: Final[float] = 0.5
_BLUR_KERNELS: Final[tuple[int, ...]] = (3, 5)
_ALPHA_RANGE: Final[tuple[float, float]] = (0.7, 1.3)
_BETA_RANGE: Final[tuple[float, float]] = (-30.0, 30.0)
_NOISE_SIGMA_MAX: Final[float] = 8.0


@dataclass(frozen=True, slots=True)
class PlateStyle:
    """Estilo de placa sintética.

    Args:
        name: Identificador del estilo.
        pattern: Patrón `L`/`D` del texto principal.
        size_mm: Tamaño (ancho, alto) de la placa en milímetros.
        char_height_mm: Alto nominal de los caracteres principales en milímetros.
        bottom_text: Texto inferior fijo, o `None` para elegir un municipio al azar.
        bottom_height_mm: Alto nominal del texto inferior en milímetros.
        background_bgr: Color de fondo en BGR.
    """

    name: str
    pattern: str
    size_mm: tuple[int, int]
    char_height_mm: float
    bottom_text: str | None
    bottom_height_mm: float
    background_bgr: tuple[int, int, int]


STYLES: Final[tuple[PlateStyle, ...]] = (
    PlateStyle("car_yellow", "LLLDDD", (330, 160), 80.0, None, 22.0, YELLOW_BGR),
    PlateStyle("car_white", "LLLDDD", (330, 160), 80.0, None, 22.0, WHITE_BGR),
    PlateStyle("moto", "LLLDDL", (235, 105), 54.0, "COLOMBIA", 10.5, YELLOW_BGR),
    PlateStyle("motocarro_yellow", "DDDLLL", (235, 105), 54.0, "COLOMBIA", 10.5, YELLOW_BGR),
    PlateStyle("motocarro_white", "DDDLLL", (235, 105), 54.0, "COLOMBIA", 10.5, WHITE_BGR),
)


def random_text(pattern: str, rng: random.Random) -> str:
    """Genera un texto de placa sintético siguiendo un patrón `L`/`D`.

    Args:
        pattern: Patrón con `L` (letra) y `D` (dígito).
        rng: Generador aleatorio determinista.

    Returns:
        Texto generado.
    """
    return "".join(rng.choice(LETTERS) if char == "L" else rng.choice(DIGITS) for char in pattern)


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Carga una fuente TrueType o falla con `TrainingError`.

    Args:
        font_path: Ruta de la fuente.
        size: Tamaño en píxeles.

    Returns:
        Fuente cargada.

    Raises:
        TrainingError: si Pillow no puede cargar la fuente.
    """
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError as exc:
        raise TrainingError(f"fuente no disponible: {font_path.name}") from exc


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_size: int,
    max_width: float,
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    """Busca el mayor tamaño de fuente cuyo ancho no supere `max_width`.

    Args:
        draw: Contexto de dibujo para medir el texto.
        text: Texto a medir.
        font_path: Ruta de la fuente.
        max_size: Tamaño inicial en píxeles.
        max_width: Ancho máximo permitido en píxeles.

    Returns:
        Fuente elegida y su `textbbox`.
    """
    size = max(1, max_size)
    while size > 1:
        font = _load_font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font, bbox
        size -= 1
    font = _load_font(font_path, 1)
    return font, draw.textbbox((0, 0), text, font=font)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    bbox: tuple[int, int, int, int],
    width: int,
    band: tuple[int, int],
) -> None:
    """Dibuja `text` centrado en horizontal dentro de una franja vertical.

    Args:
        draw: Contexto de dibujo.
        text: Texto a dibujar.
        font: Fuente cargada.
        bbox: `textbbox` del texto con `font`.
        width: Ancho de la placa en píxeles.
        band: Franja vertical `(y_inicio, y_fin)` en píxeles.
    """
    x = (width - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = band[0] + ((band[1] - band[0]) - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=_INK_RGB)


def render_plate(
    text: str,
    style: PlateStyle,
    font_path: Path,
    px_per_mm: float,
    rng: random.Random,
) -> npt.NDArray[np.uint8]:
    """Renderiza una placa sintética y devuelve su imagen BGR.

    Args:
        text: Texto principal de la placa.
        style: Estilo de placa.
        font_path: Ruta de la fuente TrueType.
        px_per_mm: Escala en píxeles por milímetro.
        rng: Generador aleatorio determinista (municipio si `style.bottom_text`
            es `None`).

    Returns:
        Imagen BGR `uint8` contigua de `alto x ancho x 3`.

    Raises:
        TrainingError: si la fuente no existe o Pillow no puede cargarla.
    """
    if not font_path.is_file():
        raise TrainingError(f"fuente no disponible: {font_path.name}")
    width = round(style.size_mm[0] * px_per_mm)
    height = round(style.size_mm[1] * px_per_mm)
    background = (
        style.background_bgr[2],
        style.background_bgr[1],
        style.background_bgr[0],
    )
    canvas = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(canvas)
    border = max(1, round(_BORDER_MM * px_per_mm))
    draw.rectangle((0, 0, width - 1, height - 1), outline=_INK_RGB, width=border)

    bottom_px = round(style.bottom_height_mm * px_per_mm)
    font, bbox = _fit_font(
        draw,
        text,
        font_path,
        round(style.char_height_mm * px_per_mm),
        _MAIN_WIDTH_RATIO * width,
    )
    _draw_centered(draw, text, font, bbox, width, (0, height - bottom_px))

    label = style.bottom_text if style.bottom_text is not None else rng.choice(MUNICIPALITIES)
    font, bbox = _fit_font(
        draw,
        label,
        font_path,
        round(style.bottom_height_mm * px_per_mm),
        _BOTTOM_WIDTH_RATIO * width,
    )
    _draw_centered(draw, label, font, bbox, width, (height - bottom_px, height))

    return np.ascontiguousarray(np.asarray(canvas)[:, :, ::-1])


def augment(image: npt.NDArray[np.uint8], rng: random.Random) -> npt.NDArray[np.uint8]:
    """Aplica rotación, desenfoque, brillo/contraste y ruido a una placa.

    Args:
        image: Imagen BGR `uint8`.
        rng: Generador aleatorio determinista.

    Returns:
        Imagen BGR `uint8` con la misma forma que `image`.
    """
    height, width = image.shape[:2]
    angle = rng.uniform(-_ROTATION_DEG, _ROTATION_DEG)
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    result = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
    if rng.random() < _BLUR_PROBABILITY:
        ksize = rng.choice(_BLUR_KERNELS)
        result = cv2.GaussianBlur(result, (ksize, ksize), 0.0)
    result = cv2.convertScaleAbs(
        result, alpha=rng.uniform(*_ALPHA_RANGE), beta=rng.uniform(*_BETA_RANGE)
    )
    sigma = rng.uniform(0.0, _NOISE_SIGMA_MAX)
    noise = np.fromiter(
        (rng.gauss(0.0, sigma) for _ in range(result.size)),
        dtype=np.float32,
        count=result.size,
    ).reshape(result.shape)
    noisy = np.clip(result.astype(np.float32) + noise, 0.0, 255.0).astype(np.uint8)
    return noisy


def _validate_output_dir(output_dir: Path) -> Path:
    """Valida el directorio de salida del dataset.

    Args:
        output_dir: Directorio de salida.

    Returns:
        Ruta resuelta del directorio de salida.

    Raises:
        TrainingError: si `output_dir` queda fuera de `DATASETS_DIR` o ya existe.
    """
    resolved = output_dir.resolve()
    datasets_root = DATASETS_DIR.resolve()
    if datasets_root not in resolved.parents and resolved != datasets_root:
        raise TrainingError(f"output_dir fuera de DATASETS_DIR: {output_dir}")
    if resolved.exists():
        raise TrainingError(f"output_dir ya existe: {output_dir}")
    return resolved


def _write_annotations(split_dir: Path, rows: Sequence[tuple[str, str]]) -> None:
    """Escribe el `annotations.csv` de un split.

    Args:
        split_dir: Directorio del split (`train` o `val`).
        rows: Filas `(image_path, plate_text)`.
    """
    with (split_dir / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("image_path", "plate_text"))
        writer.writerows(rows)


def generate_dataset(
    output_dir: Path,
    count: int,
    val_fraction: float,
    seed: int,
    font_path: Path,
) -> tuple[int, int]:
    """Genera un dataset sintético de placas en el formato de fast-plate-ocr.

    Args:
        output_dir: Directorio de salida, dentro de `DATASETS_DIR` y sin existir.
        count: Número total de muestras.
        val_fraction: Fracción inicial de muestras asignadas al split `val`.
        seed: Semilla del generador aleatorio.
        font_path: Ruta de la fuente TrueType.

    Returns:
        Par `(train_count, val_count)`.

    Raises:
        TrainingError: si `output_dir` no es válido, `count < 1` o
            `val_fraction` queda fuera de `[0, 1)`.
    """
    resolved = _validate_output_dir(output_dir)
    if count < 1:
        raise TrainingError(f"count inválido: {count}")
    if not 0.0 <= val_fraction < 1.0:
        raise TrainingError(f"val_fraction inválido: {val_fraction}")
    val_count = round(count * val_fraction)
    rng = random.Random(seed)
    rows: dict[str, list[tuple[str, str]]] = {"train": [], "val": []}
    for split in ("train", "val"):
        (resolved / split / "images").mkdir(parents=True)
    for index in range(count):
        split = "val" if index < val_count else "train"
        style = STYLES[index % len(STYLES)]
        text = random_text(style.pattern, rng)
        px_per_mm = rng.uniform(_MIN_PX_PER_MM, _MAX_PX_PER_MM)
        image = augment(render_plate(text, style, font_path, px_per_mm, rng), rng)
        name = f"syn_{index:06d}.png"
        cv2.imwrite(str(resolved / split / "images" / name), image)
        rows[split].append((f"images/{name}", text))
    _write_annotations(resolved / "train", rows["train"])
    _write_annotations(resolved / "val", rows["val"])
    return len(rows["train"]), len(rows["val"])


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de la CLI del generador.

    Returns:
        Parser configurado.
    """
    parser = argparse.ArgumentParser(
        description="Genera recortes sintéticos de placas colombianas."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Genera el dataset sintético desde la línea de comandos.

    Args:
        argv: Argumentos de línea de comandos (por defecto `sys.argv[1:]`).

    Returns:
        Código de salida: 0 si el dataset se genera correctamente.
    """
    args = build_parser().parse_args(argv)
    train_count, val_count = generate_dataset(
        DATASETS_DIR / args.output,
        args.count,
        args.val_fraction,
        args.seed,
        args.font,
    )
    print(f"train={train_count} val={val_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
