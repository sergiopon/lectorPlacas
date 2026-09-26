"""Punto de entrada de la CLI `lector` (composition root final, ARQUITECTURA.md §6)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from lector_placas.application.ports import KeyProvider
from lector_placas.cli import commands, composition, dataset_commands
from lector_placas.cli.evaluation_commands import register_evaluation_commands
from lector_placas.domain.errors import (
    ConfigurationError,
    CropStoreError,
    DatasetError,
    EncryptionError,
    EvaluationError,
    ExportError,
    InputValidationError,
    KeyUnavailableError,
    LectorPlacasError,
    ModelFetchError,
    ModelIntegrityError,
    ModelLoadError,
    NetworkAccessError,
    RepositoryError,
    VideoSourceError,
)
from lector_placas.infrastructure import network_guard
from lector_placas.infrastructure.config import load_config
from lector_placas.infrastructure.logging_setup import configure_logging

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/lector.yaml")
DEFAULT_REVIEW_LIMIT: Final[int] = 50
EXPORT_STATUS_CHOICES: Final[tuple[str, ...]] = (
    "confirmed",
    "unverified",
    "rejected",
    "corrected",
)
LOG_FILENAME: Final[str] = "lector.log"

logger = logging.getLogger(__name__)

_EXIT_CODES: Final[
    tuple[tuple[type[LectorPlacasError] | tuple[type[LectorPlacasError], ...], int], ...]
] = (
    (ConfigurationError, 2),
    ((InputValidationError, VideoSourceError), 3),
    ((ModelIntegrityError, ModelLoadError, ModelFetchError), 4),
    ((KeyUnavailableError, EncryptionError), 5),
    ((RepositoryError, CropStoreError, ExportError), 6),
    (NetworkAccessError, 7),
    ((EvaluationError, DatasetError), 8),
)


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de la CLI `lector` con todos sus subcomandos.

    Returns:
        Parser listo para `parse_args`; el subcomando es obligatorio.
    """
    parser = argparse.ArgumentParser(prog="lector")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_key_parser(subparsers)
    _add_models_parser(subparsers)
    _add_process_parser(subparsers)
    _add_review_parser(subparsers)
    _add_export_parser(subparsers)
    _add_purge_parser(subparsers)
    register_evaluation_commands(subparsers)
    dataset_commands.register_dataset_commands(subparsers)
    return parser


def _add_key_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `key init`."""
    key_parser = subparsers.add_parser("key")
    key_sub = key_parser.add_subparsers(dest="key_command", required=True)
    init_parser = key_sub.add_parser("init")
    init_parser.set_defaults(handler=commands.cmd_key_init, network=False, key="create")


def _add_models_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `models fetch` y `models verify`."""
    models_parser = subparsers.add_parser("models")
    models_sub = models_parser.add_subparsers(dest="models_command", required=True)
    fetch_parser = models_sub.add_parser("fetch")
    fetch_parser.set_defaults(handler=commands.cmd_models_fetch, network=True)
    verify_parser = models_sub.add_parser("verify")
    verify_parser.set_defaults(handler=commands.cmd_models_verify, network=False)


def _add_process_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `process VIDEO [--profile NOMBRE]`."""
    process_parser = subparsers.add_parser("process")
    process_parser.add_argument("video", type=Path)
    process_parser.add_argument("--profile", default=None)
    process_parser.set_defaults(handler=commands.cmd_process, network=False, key="load")


def _add_review_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `review [--limit N]`."""
    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("--limit", type=int, default=DEFAULT_REVIEW_LIMIT)
    review_parser.set_defaults(handler=commands.cmd_review, network=False, key="load")


def _add_export_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `export [--status {...}]`."""
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--status", choices=EXPORT_STATUS_CHOICES, default=None)
    export_parser.set_defaults(handler=commands.cmd_export, network=False, key="load")


def _add_purge_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Agrega `purge`."""
    purge_parser = subparsers.add_parser("purge")
    purge_parser.set_defaults(handler=commands.cmd_purge, network=False, key="load")


def exit_code_for(error: BaseException) -> int:
    """Traduce una excepción en el código de salida del proceso (docs/02-contratos.md §7).

    Args:
        error: excepción capturada en `main`.

    Returns:
        El código de salida asociado a su tipo más específico; 1 si no coincide con
        ninguno de los casos previstos.
    """
    for error_types, code in _EXIT_CODES:
        if isinstance(error, error_types):
            return code
    return 1


def _prefetch_keys(args: argparse.Namespace) -> KeyProvider | None:
    """Lee (o crea) la clave maestra antes de bloquear la red (SEG-20).

    El keyring del sistema (SecretService) se alcanza por D-Bus sobre un socket Unix, que
    `block_network()` también bloquea; el proveedor cachea la clave y los comandos lo reutilizan.

    Args:
        args: argumentos del subcomando; `args.key` es `"create"`, `"load"` o no existe.

    Returns:
        El proveedor con la clave ya cargada, o `None` si el subcomando no usa la clave.
    """
    mode = getattr(args, "key", None)
    if mode is None:
        return None
    keys = composition.build_key_provider(mode == "create")
    keys.master_key()
    return keys


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la CLI `lector`.

    Aplica la máscara de creación de archivos antes que cualquier otra instrucción (SEG-04),
    analiza los argumentos, carga la configuración, configura el logging, bloquea la red
    salvo en `models fetch` (SEG-20) y despacha al manejador del subcomando.

    Args:
        argv: argumentos de línea de comandos; `None` usa `sys.argv[1:]`.

    Returns:
        Código de salida del proceso.
    """
    os.umask(0o077)
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        configure_logging(
            config.logging.level, config.under_root(config.paths.log_dir) / LOG_FILENAME
        )
        args.keys = _prefetch_keys(args)
        if not args.network:
            network_guard.block_network()
        return args.handler(args, config)  # type: ignore[no-any-return]
    except LectorPlacasError as error:
        logger.error("comando fallido error=%s", type(error).__name__)
        sys.stderr.write(f"error: {error}\n")
        return exit_code_for(error)
    except Exception:  # último nivel permitido para `except Exception`, ARQUITECTURA §6
        logger.exception("error inesperado")
        sys.stderr.write("error inesperado; revise logs/lector.log\n")
        return 1
