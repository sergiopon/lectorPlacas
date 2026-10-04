"""Punto de entrada para lector-web: aplicación FastAPI con frontend."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import uvicorn

from lector_placas.application.ports import KeyProvider
from lector_placas.cli import composition
from lector_placas.domain.errors import KeyUnavailableError, LectorPlacasError
from lector_placas.infrastructure import network_guard
from lector_placas.infrastructure.config import AppConfig, load_config
from lector_placas.infrastructure.logging_setup import configure_logging
from lector_placas.web.factory import create_app
from lector_placas.web.security import SessionAuth, allowed_hosts_for

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/lector.yaml")
LOG_FILENAME: Final[str] = "lector.log"
HOST: Final[str] = "127.0.0.1"
FRONTEND_DIST: Final[Path] = Path("frontend/dist")
KEY_HINT: Final[str] = "Cree la clave con: lector key init"
MAX_PORT: Final[int] = 65535


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parsea argumentos de línea de comandos.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Parsed arguments with config, port, and no_browser attributes.
    """
    parser = argparse.ArgumentParser(prog="lector-web")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Ruta del archivo de configuración",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Puerto local (0 para asignar automáticamente)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="No abre el navegador automáticamente",
    )
    return parser.parse_args(argv)


def bind_socket(port: int) -> socket.socket:
    """Crea y vincula un socket TCP a 127.0.0.1.

    Args:
        port: puerto (0 para dejar que el sistema asigne uno libre).

    Returns:
        Socket vinculado y listo para aceptar conexiones.

    Raises:
        ValueError: si port no está en [0, MAX_PORT].
        OSError: si hay un error al vincular el socket.
    """
    if not 0 <= port <= MAX_PORT:
        raise ValueError(f"puerto inválido: {port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, port))
    return sock


def launch_url(port: int, token: str) -> str:
    """Genera la URL de inicio con el token.

    Args:
        port: puerto de la aplicación.
        token: token de inicio de sesión.

    Returns:
        URL completa con el token.
    """
    return f"http://{HOST}:{port}/auth?token={token}"


def _serve(config: AppConfig, keys: KeyProvider, sock: socket.socket, no_browser: bool) -> int:
    """Crea la app, la sirve en el socket y lo cierra al terminar.

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra.
        sock: socket vinculado a 127.0.0.1.
        no_browser: si es `True`, no abre el navegador.

    Returns:
        0 al terminar el servidor.
    """
    port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    app = create_app(
        config,
        keys,
        SessionAuth(token),
        allowed_hosts_for(port),
        static_dir=config.under_root(FRONTEND_DIST),
    )
    url = launch_url(port, token)
    sys.stdout.write(f"lectorPlacas web en http://{HOST}:{port}/\nAbra: {url}\n")
    if not no_browser:
        webbrowser.open(url)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=HOST,
            port=port,
            lifespan="on",
            log_level="warning",
            access_log=False,
            server_header=False,
            date_header=False,
        )
    )
    server.run(sockets=[sock])
    sock.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de lector-web.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si éxito, 1 si error).
    """
    os.umask(0o077)
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        configure_logging(
            config.logging.level, config.under_root(config.paths.log_dir) / LOG_FILENAME
        )
        keys = composition.build_key_provider(False)
        keys.master_key()
    except LectorPlacasError as error:
        sys.stderr.write(f"lector-web: {error}\n")
        if isinstance(error, KeyUnavailableError):
            sys.stderr.write(f"{KEY_HINT}\n")
        return 1
    try:
        network_guard.block_network()
        try:
            sock = bind_socket(args.port)
        except (OSError, ValueError):
            sys.stderr.write(f"lector-web: no se pudo abrir el puerto {args.port}\n")
            return 1
        return _serve(config, keys, sock, args.no_browser)
    except Exception:  # último nivel permitido para except Exception, ARQUITECTURA §6
        logging.getLogger(__name__).exception("error inesperado")
        return 1
