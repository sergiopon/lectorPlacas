from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.cli.main import build_parser, exit_code_for
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
    NetworkAccessError,
    RepositoryError,
    UnsafePathError,
    VideoSourceError,
)


def test_parser_process() -> None:
    args = build_parser().parse_args(
        ["--config", "c.yaml", "process", "v.mp4", "--profile", "parqueadero"]
    )
    assert (args.config, args.video, args.profile, args.network) == (
        Path("c.yaml"),
        Path("v.mp4"),
        "parqueadero",
        False,
    )


def test_parser_defaults_and_network_flag() -> None:
    parser = build_parser()
    assert parser.parse_args(["review"]).limit == 50
    assert parser.parse_args(["purge"]).config == Path("config/lector.yaml")
    assert parser.parse_args(["models", "fetch"]).network is True
    assert parser.parse_args(["models", "verify"]).network is False
    assert parser.parse_args(["export", "--status", "unverified"]).status == "unverified"
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.parametrize(
    "error,code",
    [
        (ConfigurationError("x"), 2),
        (InputValidationError("x"), 3),
        (UnsafePathError("x"), 3),
        (VideoSourceError("x"), 3),
        (ModelIntegrityError("x"), 4),
        (ModelFetchError("x"), 4),
        (KeyUnavailableError("x"), 5),
        (EncryptionError("x"), 5),
        (RepositoryError("x"), 6),
        (CropStoreError("x"), 6),
        (ExportError("x"), 6),
        (NetworkAccessError("x"), 7),
        (EvaluationError("x"), 8),
        (DatasetError("x"), 8),
        (LectorPlacasError("x"), 1),
        (RuntimeError("x"), 1),
    ],
)
def test_exit_codes(error: BaseException, code: int) -> None:
    assert exit_code_for(error) == code
