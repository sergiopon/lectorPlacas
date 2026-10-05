"""Tests de aceptación adicionales.

Cubren casos borde que la spec no enumera explícitamente: claves extra dentro de un
perfil (el esquema de perfiles es cerrado), letras minúsculas en el mapa de confusiones
(solo se admiten pares letra-mayúscula/dígito) y rutas con `..` dentro de
`input.allowed_dirs` (no solo en `paths`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from lector_placas.domain.errors import ConfigurationError
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "config" / "lector.yaml"


def base_data() -> dict[str, Any]:
    return yaml.safe_load(REAL.read_text(encoding="utf-8"))


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    target = config_dir / "lector.yaml"
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    return target


def test_profile_with_extra_keys_is_rejected(tmp_path: Path) -> None:
    """Una clave extra dentro de un perfil rompe el esquema cerrado (`extra="forbid"`)."""
    data = base_data()
    data["profiles"]["calle_lenta"]["extra"] = True
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_confusions_with_lowercase_letter_is_rejected(tmp_path: Path) -> None:
    """El mapa de confusiones solo admite letras mayúsculas: una minúscula es inválida."""
    data = base_data()
    data["consolidation"]["confusions"] = [["o", "0"]]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))


def test_allowed_dir_with_dotdot_is_rejected(tmp_path: Path) -> None:
    """Un directorio permitido con `..` se rechaza igual que las rutas de `paths`."""
    data = base_data()
    data["input"]["allowed_dirs"] = ["../fuera"]
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, data))
