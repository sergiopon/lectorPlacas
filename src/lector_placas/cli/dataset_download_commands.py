"""Subcomandos `lector dataset download` y `lector dataset prepare` (con red, SEG-20).

`download` baja los datasets de `config/datasets.yaml` desde Roboflow y regenera el
manifiesto de fuentes; `prepare` encadena esa descarga con `merge-detection` y
`chars-to-ocr`. Son las dos únicas operaciones con red además de `models fetch`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from lector_placas.cli import dataset_commands
from lector_placas.datasets.chars_to_ocr import chars_to_ocr
from lector_placas.datasets.merge_detection import merge_detection
from lector_placas.datasets.registry import (
    DatasetEntry,
    DatasetRegistry,
    load_registry,
    write_sources_file,
)
from lector_placas.domain.errors import DatasetError
from lector_placas.infrastructure.dataset_fetcher import (
    api_key_from_env,
    default_http_get,
    download_dataset,
)
from lector_placas.infrastructure.paths import resolve_within

if TYPE_CHECKING:
    from lector_placas.infrastructure.config import AppConfig

REGISTRY_FILE: Final[Path] = Path("config/datasets.yaml")
SOURCES_FILE: Final[str] = "sources.yaml"
MERGED_OUTPUT: Final[str] = "merged"
OCR_OUTPUT: Final[str] = "ocr_colombia"


def register_download_commands(
    dataset_sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Agrega los subcomandos `download` y `prepare` al subparser `dataset`.

    Args:
        dataset_sub: subparsers del comando `dataset`.
    """
    download_parser = dataset_sub.add_parser("download")
    download_parser.add_argument("--only", nargs="+", default=None)
    download_parser.set_defaults(handler=cmd_download, network=True)
    prepare_parser = dataset_sub.add_parser("prepare")
    prepare_parser.set_defaults(handler=cmd_prepare, network=True)


def cmd_download(args: argparse.Namespace, config: AppConfig) -> int:
    """Descarga los datasets del registro y regenera el manifiesto de fuentes.

    Args:
        args: argumentos con `only` (nombres a descargar, o `None` para todos).
        config: configuración de la aplicación, usada como raíz de las rutas.

    Returns:
        El código de salida 0.

    Raises:
        ConfigurationError: Si falta la variable de entorno con la clave de API.
        DatasetError: Si el registro no valida, un nombre de `--only` no existe,
            una descarga falla o no hay datasets de detección descargados.
    """
    api_key = api_key_from_env(os.environ)
    registry = load_registry(config.root_dir / REGISTRY_FILE)
    for entry in _select(registry, args.only):
        _download_entry(entry, registry.format, api_key, config)
    written = write_sources_file(registry, _raw_root(config, "detector"), _sources_path(config))
    sys.stdout.write(f"{SOURCES_FILE}: {written} fuentes\n")
    return 0


def cmd_prepare(args: argparse.Namespace, config: AppConfig) -> int:
    """Encadena descarga, unión del detector y conversión a recortes de OCR.

    Args:
        args: argumentos del subcomando (ninguno propio).
        config: configuración de la aplicación, usada como raíz de las rutas.

    Returns:
        El código de salida 0.

    Raises:
        ConfigurationError: Si falta la variable de entorno con la clave de API.
        DatasetError: Si alguna descarga, unión o conversión falla.
    """
    args.only = None
    cmd_download(args, config)
    _prepare_merged(config)
    _prepare_ocr(config)
    return 0


def _select(registry: DatasetRegistry, only: list[str] | None) -> tuple[DatasetEntry, ...]:
    """Filtra las entradas del registro por los nombres pedidos en `--only`."""
    if only is None:
        return registry.datasets
    known = {entry.name for entry in registry.datasets}
    unknown = sorted(name for name in only if name not in known)
    if unknown:
        raise DatasetError(f"dataset desconocido: {', '.join(unknown)}")
    selected = set(only)
    return tuple(entry for entry in registry.datasets if entry.name in selected)


def _raw_root(config: AppConfig, target: str) -> Path:
    """Devuelve la raíz de descargas del destino pedido (`detector` u `ocr`)."""
    if target == "detector":
        relative = dataset_commands.DETECTOR_ROOT / "datasets" / dataset_commands.RAW_DIR
    else:
        relative = dataset_commands.OCR_DATASETS_ROOT / dataset_commands.RAW_DIR
    return resolve_within(config.root_dir, relative)


def _sources_path(config: AppConfig) -> Path:
    """Devuelve la ruta del manifiesto de fuentes del detector."""
    return resolve_within(config.root_dir, dataset_commands.DETECTOR_ROOT / SOURCES_FILE)


def _download_entry(entry: DatasetEntry, fmt: str, api_key: str, config: AppConfig) -> None:
    """Descarga un dataset si su carpeta destino no tiene ya un `data.yaml`."""
    destination = resolve_within(_raw_root(config, entry.target), Path(entry.name))
    if (destination / "data.yaml").exists():
        sys.stdout.write(f"{entry.name}: ya descargado\n")
        return
    version = download_dataset(
        default_http_get,
        api_key,
        entry.workspace,
        entry.project,
        fmt,
        destination,
        sleep=time.sleep,
    )
    sys.stdout.write(f"{entry.name}: descargado (versión {version})\n")


def _prepare_merged(config: AppConfig) -> None:
    """Une los datasets de detección descargados si la salida no existe."""
    output = resolve_within(
        config.root_dir, dataset_commands.DETECTOR_ROOT / "datasets" / MERGED_OUTPUT
    )
    if output.exists():
        sys.stdout.write(f"{MERGED_OUTPUT}: ya preparado\n")
        return
    summary = merge_detection(_sources_path(config), _raw_root(config, "detector"), output)
    sys.stdout.write(
        f"train={summary.train_images} val={summary.val_images} "
        f"duplicados={summary.dropped_duplicates} cajas={summary.boxes}\n"
    )


def _prepare_ocr(config: AppConfig) -> None:
    """Convierte el dataset de OCR descargado si la salida no existe."""
    output = resolve_within(config.root_dir, dataset_commands.OCR_DATASETS_ROOT / OCR_OUTPUT)
    if output.exists():
        sys.stdout.write(f"{OCR_OUTPUT}: ya preparado\n")
        return
    source = resolve_within(_raw_root(config, "ocr"), Path("ocr_placas_colombia"))
    summary = chars_to_ocr(source, output, config.plate_catalog())
    sys.stdout.write(
        f"train={summary.train_crops} val={summary.val_crops} "
        f"omitidos={summary.skipped} duplicados={summary.dropped_duplicates}\n"
    )
