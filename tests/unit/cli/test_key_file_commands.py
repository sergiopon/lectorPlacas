from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lector_placas.adapters.security.file_key_provider import KEY_FILE_ENV, FileKeyProvider
from lector_placas.adapters.security.keyring_key_provider import KeyringKeyProvider
from lector_placas.cli import commands, composition
from lector_placas.cli import main as cli_main
from tests.fixtures.fakes import FakeKeyProvider


def test_build_key_provider_selects_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selecciona FileKeyProvider cuando LECTOR_KEY_FILE está definida."""
    monkeypatch.setenv(KEY_FILE_ENV, "/x/k")
    provider = composition.build_key_provider(False)
    assert isinstance(provider, FileKeyProvider)

    monkeypatch.delenv(KEY_FILE_ENV)
    provider = composition.build_key_provider(False)
    assert isinstance(provider, KeyringKeyProvider)

    monkeypatch.setenv(KEY_FILE_ENV, "")
    provider = composition.build_key_provider(False)
    assert isinstance(provider, KeyringKeyProvider)


def test_parser_registers_key_file_commands() -> None:
    """Registra los subcomandos key export-file e init-file."""
    parser = cli_main.build_parser()

    # Test export-file
    args = parser.parse_args(["key", "export-file", "/tmp/k"])
    assert args.key == "load"
    assert args.network is False
    assert args.path == Path("/tmp/k")

    # Test init-file
    args = parser.parse_args(["key", "init-file", "/tmp/k"])
    assert getattr(args, "key", None) is None
    assert args.network is False
    assert args.path == Path("/tmp/k")


def _run_command(cmd_func, args, config) -> tuple[int, str]:
    """Ejecuta un comando y captura su salida."""
    captured_output = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured_output
        result = cmd_func(args, config)
    finally:
        sys.stdout = old_stdout
    return result, captured_output.getvalue()


def test_cmd_key_init_file_and_export(tmp_path: Path) -> None:
    """Crea y exporta claves en archivos."""
    config = MagicMock()

    # Test init-file
    key_file = tmp_path / "k1"
    args = argparse.Namespace(path=key_file)
    result, output = _run_command(commands.cmd_key_init_file, args, config)

    assert result == 0
    assert output == "clave maestra nueva escrita en el archivo indicado (0400)\n"

    # Verificar que se puede leer con FileKeyProvider
    provider = FileKeyProvider(key_file)
    assert len(provider.master_key()) == 32

    # Test export-file
    export_file = tmp_path / "k2"
    args = argparse.Namespace(path=export_file, keys=FakeKeyProvider())
    result, output = _run_command(commands.cmd_key_export_file, args, config)

    assert result == 0
    assert output == "clave maestra copiada al archivo indicado (0400)\n"

    # Verificar que contiene la misma clave
    provider = FileKeyProvider(export_file)
    assert provider.master_key() == FakeKeyProvider().master_key()


def test_cmd_key_init_message_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El mensaje de init cambia cuando LECTOR_KEY_FILE está definida."""
    config = MagicMock()

    # Con LECTOR_KEY_FILE definida
    key_file = tmp_path / "key"
    monkeypatch.setenv(KEY_FILE_ENV, str(key_file))

    args = argparse.Namespace(keys=FakeKeyProvider())
    result, output = _run_command(commands.cmd_key_init, args, config)

    assert result == 0
    assert output == "clave maestra disponible en el archivo de clave\n"
