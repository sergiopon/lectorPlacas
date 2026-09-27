"""Arranque de la GUI `lector-gui`: umask, configuración, clave, guardia y ventana (ADR-015)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Final, cast

from PySide6.QtWidgets import QApplication, QMessageBox

from lector_placas.application.ports import KeyProvider
from lector_placas.cli import composition
from lector_placas.domain.errors import KeyUnavailableError, LectorPlacasError
from lector_placas.gui.main_window import WINDOW_TITLE, MainWindow
from lector_placas.gui.session import open_session
from lector_placas.infrastructure import network_guard
from lector_placas.infrastructure.config import AppConfig, load_config
from lector_placas.infrastructure.logging_setup import configure_logging

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/lector.yaml")
LOG_FILENAME: Final[str] = "lector.log"
KEY_HINT: Final[str] = "Cree la clave con: lector key init"
UNEXPECTED_MESSAGE: Final[str] = "error inesperado; revise logs/lector.log"

logger = logging.getLogger(__name__)


def prepare(argv: Sequence[str] | None) -> tuple[AppConfig, KeyProvider]:
    """Analiza los argumentos, carga la configuración, el logging y la clave maestra.

    La clave se lee **antes** de bloquear la red (SEG-20). No crea la clave: si no existe,
    el proveedor lanza `KeyUnavailableError`.

    Args:
        argv: argumentos de línea de comandos; `None` usa `sys.argv[1:]`.

    Returns:
        La configuración validada y el proveedor con la clave ya cargada.

    Raises:
        LectorPlacasError: si la configuración, el logging o la clave fallan.
    """
    parser = argparse.ArgumentParser(prog="lector-gui")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    configure_logging(config.logging.level, config.under_root(config.paths.log_dir) / LOG_FILENAME)
    keys = composition.build_key_provider(False)
    keys.master_key()
    return config, keys


def _create_application() -> QApplication:
    """Devuelve la `QApplication` existente o crea una nueva con la aplicación nombrada."""
    existing = QApplication.instance()
    app = cast("QApplication", existing) if existing is not None else QApplication(["lector-gui"])
    app.setApplicationName("lectorPlacas")
    return app


def _exec(app: QApplication) -> int:
    """Ejecuta el bucle de eventos de Qt y devuelve su código de salida."""
    return app.exec()


def _try_prepare(
    argv: Sequence[str] | None,
) -> tuple[AppConfig, KeyProvider] | LectorPlacasError:
    """Llama a `prepare` y devuelve el error en vez de propagarlo."""
    try:
        return prepare(argv)
    except LectorPlacasError as error:
        return error


def _report_startup_failure(error: LectorPlacasError) -> int:
    """Muestra el diálogo de arranque fallido, lo registra y devuelve el código de error."""
    text = str(error)
    if isinstance(error, KeyUnavailableError):
        text = f"{text}\n{KEY_HINT}"
    QMessageBox.critical(None, WINDOW_TITLE, text)
    logger.error("arranque fallido error=%s", type(error).__name__)
    return 1


def _handle_unexpected(
    exc_type: type[BaseException], exc_value: BaseException, exc_tb: TracebackType | None
) -> None:
    """Registra una excepción no controlada sin cerrar la ventana (ARQUITECTURA §6)."""
    logger.critical("error no controlado", exc_info=(exc_type, exc_value, exc_tb))
    QMessageBox.critical(None, WINDOW_TITLE, UNEXPECTED_MESSAGE)


def _install_excepthook() -> None:
    """Instala el manejador de excepciones no controladas de la GUI."""
    sys.excepthook = _handle_unexpected


def _run_window(app: QApplication, config: AppConfig, keys: KeyProvider) -> int:
    """Abre la sesión, muestra la ventana principal y devuelve el código del bucle de Qt."""
    _install_excepthook()
    try:
        session, purge = open_session(config, keys)
    except LectorPlacasError as error:
        QMessageBox.critical(None, WINDOW_TITLE, str(error))
        logger.error("apertura de sesión fallida error=%s", type(error).__name__)
        return 1
    window = MainWindow(session, purge)
    window.show()
    try:
        return _exec(app)
    finally:
        session.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la GUI `lector-gui`.

    Aplica la máscara de archivos, prepara la configuración y la clave, bloquea la red
    siempre (SEG-20) y solo entonces crea la `QApplication`.

    Args:
        argv: argumentos de línea de comandos; `None` usa `sys.argv[1:]`.

    Returns:
        Código de salida del proceso.
    """
    os.umask(0o077)
    try:
        prepared = _try_prepare(argv)
        network_guard.block_network()
        app = _create_application()
        if isinstance(prepared, LectorPlacasError):
            return _report_startup_failure(prepared)
        config, keys = prepared
        return _run_window(app, config, keys)
    except Exception:  # último nivel permitido para `except Exception`, ARQUITECTURA §6
        logger.exception("error inesperado")
        return 1
