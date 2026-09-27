from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lector_placas.cli import main as cli_main
from lector_placas.cli.main import build_parser

ROOT = Path(__file__).resolve().parents[3]


def test_parser_download_and_prepare_use_network() -> None:
    parser = build_parser()
    download = parser.parse_args(["dataset", "download", "--only", "usco"])
    assert (download.network, download.only) == (True, ["usco"])
    assert parser.parse_args(["dataset", "prepare"]).network is True
    assert getattr(download, "key", None) is None


def test_missing_api_key_exits_2_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml", "datasets.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    code = cli_main.main(
        ["--config", str(tmp_path / "config" / "lector.yaml"), "dataset", "download"]
    )
    assert code == 2
    assert not (tmp_path / "training").exists()


def test_prepare_merged_removes_partial_output_when_merge_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from lector_placas.cli import dataset_download_commands as commands
    from lector_placas.domain.errors import DatasetError

    def broken(sources: Path, raw_root: Path, output: Path) -> None:
        output.mkdir(parents=True)
        (output / "data.yaml").write_text("parcial", encoding="utf-8")
        raise DatasetError("etiqueta inválida: a.txt:1")

    monkeypatch.setattr(commands, "merge_detection", broken)
    output = tmp_path / "training" / "detector" / "datasets" / "merged"
    with pytest.raises(DatasetError):
        commands._prepare_merged(SimpleNamespace(root_dir=tmp_path))
    assert not output.exists()
    output.mkdir(parents=True)  # una carpeta vacía tampoco cuenta como "ya preparado"
    with pytest.raises(DatasetError):
        commands._prepare_merged(SimpleNamespace(root_dir=tmp_path))
    assert not output.exists()
