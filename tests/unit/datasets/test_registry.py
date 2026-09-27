from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lector_placas.datasets.registry import (
    DatasetEntry,
    load_registry,
    resolve_plate_classes,
    write_sources_file,
)
from lector_placas.domain.errors import DatasetError

ROOT = Path(__file__).resolve().parents[3]


def test_real_registry_is_valid() -> None:
    registry = load_registry(ROOT / "config" / "datasets.yaml")
    assert [d.name for d in registry.datasets] == [
        "usco",
        "placas_motos_carros",
        "motos_placas",
        "ocr_placas_colombia",
    ]
    assert registry.datasets[-1].target == "ocr"


def make_raw(tmp_path: Path, name: str, names: object) -> Path:
    directory = tmp_path / "raw" / name
    directory.mkdir(parents=True)
    (directory / "data.yaml").write_text(yaml.safe_dump({"names": names}), encoding="utf-8")
    return directory


def test_resolve_auto_and_explicit(tmp_path: Path) -> None:
    registry = load_registry(ROOT / "config" / "datasets.yaml")
    explicit = registry.datasets[0]
    auto = DatasetEntry(
        name="auto", workspace="ws", project="proj", target="detector", license="CC BY 4.0"
    )
    assert resolve_plate_classes(auto, make_raw(tmp_path, "a", ["plate"])) == ("plate",)
    assert resolve_plate_classes(explicit, tmp_path) == ("placa",)
    with pytest.raises(DatasetError):
        resolve_plate_classes(auto, make_raw(tmp_path, "b", ["car", "plate"]))


def test_write_sources_only_for_downloaded(tmp_path: Path) -> None:
    registry = load_registry(ROOT / "config" / "datasets.yaml")
    make_raw(tmp_path, "usco", ["placa"])
    out = tmp_path / "sources.yaml"
    assert write_sources_file(registry, tmp_path / "raw", out) == 1
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["sources"][0]["plate_classes"] == ["placa"]
    assert (
        data["sources"][0]["url"]
        == "https://universe.roboflow.com/usco-thj9e/placas-colombia-ixdpr"
    )
    with pytest.raises(DatasetError):
        write_sources_file(registry, tmp_path / "vacio", tmp_path / "s2.yaml")
