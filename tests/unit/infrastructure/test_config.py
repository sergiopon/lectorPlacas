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


def test_real_config_has_four_profiles_with_modes() -> None:
    config = load_config(REAL)
    profile_names = list(config.profiles)
    assert profile_names == ["parqueadero", "calle_lenta", "calle_rapida", "patrulla"]
    for name in ["parqueadero", "calle_lenta", "calle_rapida"]:
        assert config.profiles[name].mode == "estatico"
    assert config.profiles["patrulla"].mode == "movil"
    for name in profile_names:
        assert config.profiles[name].camera_motion_compensation is True


def test_patrulla_profile_values() -> None:
    config = load_config(REAL)
    profile = config.profiles["patrulla"]
    assert profile.target_fps == 30
    assert profile.max_readings_per_track == 6
    assert profile.track_finalize_after_ms == 1000
    assert profile.min_readings == 2
    assert profile.confirm_threshold == 0.90
    assert profile.min_agreement == 0.60
    assert profile.min_plate_width_px == 32
    assert profile.min_sharpness == 0.0
    assert profile.max_ocr_per_frame == 8
    assert profile.vehicle_crop_margin == 0.10


def test_mobile_profile_requires_cmc(tmp_path: Path) -> None:
    data = base_data()
    data["profiles"]["patrulla"]["camera_motion_compensation"] = False
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(write(tmp_path, data))
    assert "el perfil patrulla es movil y exige camera_motion_compensation: true" in str(
        exc_info.value
    )


def test_static_profile_may_disable_cmc(tmp_path: Path) -> None:
    data = base_data()
    data["profiles"]["calle_lenta"]["camera_motion_compensation"] = False
    config = load_config(write(tmp_path, data))
    assert config.profiles["calle_lenta"].camera_motion_compensation is False


def test_invalid_mode_raises(tmp_path: Path) -> None:
    data = base_data()
    data["profiles"]["calle_lenta"]["mode"] = "otro"
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_missing_mode_or_cmc_raises(tmp_path: Path) -> None:
    data = base_data()
    del data["profiles"]["calle_lenta"]["mode"]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))

    data = base_data()
    del data["profiles"]["calle_lenta"]["camera_motion_compensation"]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_first_offending_profile_is_named(tmp_path: Path) -> None:
    data = base_data()
    data["profiles"]["patrulla"]["camera_motion_compensation"] = False
    data["profiles"]["patrulla_extra"] = copy.deepcopy(data["profiles"]["patrulla"])
    data["profiles"]["patrulla_extra"]["camera_motion_compensation"] = False
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(write(tmp_path, data))
    error_str = str(exc_info.value)
    assert "el perfil patrulla es movil" in error_str
    assert "patrulla_extra" not in error_str


def test_real_config_proximity_values() -> None:
    """Verifica que los cuatro perfiles tienen los valores correctos de proximidad."""
    config = load_config(REAL)
    for profile_name in ["parqueadero", "calle_lenta", "calle_rapida", "patrulla"]:
        profile = config.profiles[profile_name]
        assert profile.min_plate_width_px == 32
        assert profile.near_min_width_frac == 0.025
        assert profile.max_plate_vehicle_ratio == 0.5
        assert profile.roi == (0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize(
    "mutate,error_substring",
    [
        (
            lambda d: d["profiles"]["calle_lenta"].update(near_min_width_frac=0.21),
            "near_min_width_frac debe estar en [0, 0.2]: 0.21",
        ),
        (
            lambda d: d["profiles"]["calle_lenta"].update(near_min_width_frac=-0.01),
            "near_min_width_frac debe estar en [0, 0.2]: -0.01",
        ),
        (
            lambda d: d["profiles"]["calle_lenta"].update(max_plate_vehicle_ratio=0.0),
            "max_plate_vehicle_ratio debe estar en (0, 1]: 0.0",
        ),
        (
            lambda d: d["profiles"]["calle_lenta"].update(max_plate_vehicle_ratio=1.01),
            "max_plate_vehicle_ratio debe estar en (0, 1]: 1.01",
        ),
        (
            lambda d: d["profiles"]["calle_lenta"].update(roi=[0.5, 0.0, 0.4, 1.0]),
            "roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1",
        ),
    ],
)
def test_invalid_proximity_values(tmp_path: Path, mutate: Any, error_substring: str) -> None:
    """Verifica que valores inválidos de proximidad lanzan ConfigurationError."""
    data = base_data()
    mutate(data)
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(write(tmp_path, data))
    assert error_substring in str(exc_info.value)


def test_invalid_roi_wrong_length(tmp_path: Path) -> None:
    """Verifica que una ROI con longitud incorrecta causa error."""
    data = base_data()
    data["profiles"]["calle_lenta"]["roi"] = [0.0, 0.0, 1.0]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_real_config_early_stop(tmp_path: Path) -> None:
    """Verifica early_stop en los cuatro perfiles y que es obligatorio."""
    config = load_config(REAL)
    for profile_name in ["parqueadero", "calle_lenta", "calle_rapida", "patrulla"]:
        assert config.profiles[profile_name].early_stop is True
    data = base_data()
    del data["profiles"]["calle_lenta"]["early_stop"]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_real_config_dedup_window(tmp_path: Path) -> None:
    config = load_config(REAL)
    for profile_name in ["parqueadero", "calle_lenta", "calle_rapida", "patrulla"]:
        assert config.profiles[profile_name].dedup_window_ms == 30000
    for value in (600001, -1):
        data = base_data()
        data["profiles"]["calle_lenta"]["dedup_window_ms"] = value
        with pytest.raises(ConfigurationError) as info:
            load_config(write(tmp_path, data))
        assert f"dedup_window_ms debe estar en [0, 600000]: {value}" in str(info.value)
