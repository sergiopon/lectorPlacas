# tests/unit/infrastructure/test_config.py
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from lector_placas.domain.consolidation import ConsolidationPolicy
from lector_placas.domain.errors import ConfigurationError
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]
REAL = ROOT / "config" / "lector.yaml"


def base_data() -> dict[str, Any]:
    return yaml.safe_load(REAL.read_text(encoding="utf-8"))


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    target = config_dir / "lector.yaml"
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    return target


def test_real_config_loads() -> None:
    config = load_config(REAL)
    assert config.root_dir == ROOT
    assert config.default_profile == "calle_lenta"
    assert len(config.plate_catalog().formats) == 9
    assert config.confusion_map().pairs[0] == ("O", "0")
    name, profile = config.profile(None)
    assert (name, profile.target_fps) == ("calle_lenta", 15)
    assert config.consolidation_policy(profile) == ConsolidationPolicy(3, 0.90, 0.60, 0.10)
    assert config.under_root(Path("data")) == ROOT / "data"


def test_unknown_profile_raises() -> None:
    with pytest.raises(ConfigurationError):
        load_config(REAL).profile("autopista")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(version=2),
        lambda d: d["paths"].update(data_dir="/etc"),
        lambda d: d["paths"].update(data_dir="../fuera"),
        lambda d: d["input"].update(allowed_extensions=["MP4"]),
        lambda d: d["models"]["vehicle_detector"].update(input_size=600),
        lambda d: d["models"]["plate_detector"].update(backend="otro"),
        lambda d: d["tracker"].update(cmc_method="magic"),
        lambda d: d.update(default_profile="inexistente"),
        lambda d: d["profiles"]["calle_lenta"].update(confirm_threshold=1.5),
        lambda d: d["profiles"]["calle_lenta"].update(target_fps=0),
        lambda d: d["retention"].update(crops_days=100, records_days=90),
        lambda d: d["consolidation"].update(confusions=[["O", "0"], ["Q", "0"]]),
        lambda d: d["plate_formats"].append(copy.deepcopy(d["plate_formats"][0])),
        lambda d: d["plate_formats"][0].update(regex="[A-Z"),
        lambda d: d.update(extra_key=1),
        lambda d: d.update(root_dir="/tmp"),
    ],
)
def test_invalid_configs_raise(tmp_path: Path, mutate: Any) -> None:
    data = base_data()
    mutate(data)
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bad = config_dir / "lector.yaml"
    bad.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(bad)
    with pytest.raises(ConfigurationError):
        load_config(config_dir / "no-existe.yaml")
    bad.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(bad)


def test_root_dir_is_parent_of_config_dir(tmp_path: Path) -> None:
    assert load_config(write(tmp_path, base_data())).root_dir == tmp_path.resolve()
