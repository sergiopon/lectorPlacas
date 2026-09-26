# 006 - Infraestructura: configuración validada

## Objetivo
Cargar y validar `config/lector.yaml` con pydantic, y construir desde ella los objetos del dominio
(catálogo de formatos, mapa de confusiones, política de consolidación por perfil).

## Depende de
001, 002, 003, 004.

## Archivos rectores aplicables
- ARQUITECTURA.md §6, §7. docs/03-modelo-datos.md §4 (contenido y tabla de validaciones).
- reglas-seguridad.md SEG-14 (`yaml.safe_load`), SEG-13 (rutas relativas sin `..`).
- ADR-006 (perfiles), ADR-007 (consolidación).

## Archivos a crear/modificar
- `config/lector.yaml` (contenido literal de docs/03-modelo-datos.md §4, bloque YAML completo)
- `src/lector_placas/infrastructure/config.py`
- `tests/unit/infrastructure/test_config.py`

## Dependencias externas
pydantic==2.13.5, PyYAML==6.0.3 (ya instalados).

## Interfaces y tipos involucrados
```python
# del dominio (specs 001-004)
class VehicleType(StrEnum): ...
@dataclass(frozen=True, slots=True)
class PlateFormat: format_id: str; category: str; pattern: str; regex: str; verified: bool; vehicle_types: frozenset[VehicleType]; source: str
class PlateFormatCatalog:
    def __init__(self, formats: Sequence[PlateFormat]) -> None: ...
@dataclass(frozen=True, slots=True)
class ConfusionMap: pairs: tuple[tuple[str, str], ...]
@dataclass(frozen=True, slots=True)
class ConsolidationPolicy: min_readings: int; confirm_threshold: float; min_agreement: float; ambiguity_margin: float
class ConfigurationError(LectorPlacasError): ...
class DomainError(LectorPlacasError): ...
```
```python
# infrastructure/config.py — a implementar
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class PathsConfig(StrictModel):
    data_dir: Path
    models_dir: Path
    log_dir: Path
    model_manifest: Path

class InputConfig(StrictModel):
    allowed_dirs: tuple[Path, ...]            # min 1 elemento
    allowed_extensions: tuple[str, ...]       # min 1 elemento
    max_file_size_mb: int                     # 1..102400

class InferenceConfig(StrictModel):
    execution_provider: Literal["cuda", "cpu"]

class VehicleDetectorConfig(StrictModel):
    model_id: str
    input_size: int
    score_threshold: float

class PlateDetectorConfig(StrictModel):
    backend: Literal["open_image_models", "yolo"]
    model_id: str
    input_size: int
    score_threshold: float

class OcrConfig(StrictModel):
    model_id: str
    config_id: str

class ModelsConfig(StrictModel):
    vehicle_detector: VehicleDetectorConfig
    plate_detector: PlateDetectorConfig
    ocr: OcrConfig

class TrackerConfig(StrictModel):
    lost_track_buffer: int
    track_activation_threshold: float
    minimum_consecutive_frames: int
    minimum_iou_threshold_first_assoc: float
    minimum_iou_threshold_second_assoc: float
    minimum_iou_threshold_unconfirmed_assoc: float
    high_conf_det_threshold: float
    cmc_method: Literal["sparseOptFlow", "orb", "sift", "ecc"]
    cmc_downscale: int

class ProfileConfig(StrictModel):
    target_fps: float
    max_readings_per_track: int
    track_finalize_after_ms: int
    min_readings: int
    confirm_threshold: float
    min_agreement: float
    min_plate_width_px: int
    min_sharpness: float
    max_ocr_per_frame: int
    vehicle_crop_margin: float

class ConsolidationConfig(StrictModel):
    ambiguity_margin: float
    confusions: tuple[tuple[str, str], ...]

class RetentionConfig(StrictModel):
    crops_days: int
    records_days: int

class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]

class PlateFormatConfig(StrictModel):
    format_id: str
    category: str
    pattern: str
    regex: str
    verified: bool
    vehicle_types: tuple[VehicleType, ...]
    source: str

class AppConfig(StrictModel):
    version: Literal[1]
    root_dir: Path
    paths: PathsConfig
    input: InputConfig
    inference: InferenceConfig
    models: ModelsConfig
    tracker: TrackerConfig
    default_profile: str
    profiles: dict[str, ProfileConfig]
    consolidation: ConsolidationConfig
    retention: RetentionConfig
    logging: LoggingConfig
    plate_formats: tuple[PlateFormatConfig, ...]

    def under_root(self, relative: Path) -> Path: ...
    def profile(self, name: str | None) -> tuple[str, ProfileConfig]: ...
    def plate_catalog(self) -> PlateFormatCatalog: ...
    def confusion_map(self) -> ConfusionMap: ...
    def consolidation_policy(self, profile: ProfileConfig) -> ConsolidationPolicy: ...

def load_config(path: Path) -> AppConfig: ...
```

## Comportamiento esperado
1. Restricciones con `pydantic.Field` / validadores (`ValueError` con mensaje en español):
   - Umbrales (`score_threshold`, `*_threshold`, `min_agreement`, `confirm_threshold`, `ambiguity_margin`,
     `vehicle_crop_margin`): `0 <= x <= 1`.
   - `input_size`: múltiplo de 32 en [32, 1280].
   - `target_fps`: `0 < x <= 120`. Enteros de perfil (`max_readings_per_track`, `track_finalize_after_ms`,
     `min_readings`, `min_plate_width_px`, `max_ocr_per_frame`) ≥ 1. `min_sharpness >= 0`.
   - `lost_track_buffer >= 0`, `minimum_consecutive_frames >= 1`, `cmc_downscale >= 1`.
   - `allowed_extensions`: cada una empieza por `.`, es igual a su `.lower()` y tiene longitud 2..10.
   - Todas las rutas de `paths` e `input.allowed_dirs`: relativas (`not p.is_absolute()`) y sin componente `..`.
   - `model_id`/`config_id`: `^[a-z0-9][a-z0-9-]{1,63}$`.
   - Claves de `profiles`: `^[a-z_]{1,32}$`; al menos un perfil.
   - `model_validator(mode="after")` de `AppConfig`: `default_profile` existe en `profiles`;
     `1 <= retention.crops_days <= retention.records_days <= 3650`; `plate_catalog()` y `confusion_map()`
     se construyen sin error (cualquier `DomainError` se convierte en `ValueError` con su mensaje).
2. `under_root(relative)` → `self.root_dir / relative`.
3. `profile(name)`: `name is None` → usa `default_profile`; nombre inexistente → `ConfigurationError("perfil desconocido: <name>")`.
   Devuelve `(nombre, ProfileConfig)`.
4. `plate_catalog()` → `PlateFormatCatalog([PlateFormat(fid, category, pattern, regex, verified, frozenset(types), source) ...])` en el orden del YAML.
5. `confusion_map()` → `ConfusionMap(self.consolidation.confusions)`.
6. `consolidation_policy(profile)` → `ConsolidationPolicy(profile.min_readings, profile.confirm_threshold, profile.min_agreement, self.consolidation.ambiguity_margin)`.
7. `load_config(path)`:
   - Lee con `path.read_text(encoding="utf-8")`; `OSError` → `ConfigurationError("no se pudo leer la configuración: <nombre>")`.
   - `yaml.safe_load`; `yaml.YAMLError` → `ConfigurationError("YAML inválido: <nombre>")`. Si el resultado no es `dict` → `ConfigurationError`.
   - Si el YAML contiene la clave `root_dir` → `ConfigurationError("root_dir no se configura en el archivo")`.
   - `data["root_dir"] = path.resolve().parent.parent` (raíz del proyecto = padre de `config/`).
   - `AppConfig.model_validate(data)`; `pydantic.ValidationError` → `ConfigurationError` con mensaje
     `"configuración inválida: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())`.

## Casos borde y manejo de errores
- Nunca uses `yaml.load`. No hay valores por defecto implícitos: todo campo es obligatorio.

## Tests de aceptación
```python
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


@pytest.mark.parametrize("mutate", [
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
])
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
```

## Fuera de alcance
Manifiesto de modelos (spec 019); construcción de `ProcessingSettings` y del tracker (spec 028).

## Definition of Done
- [ ] `config/lector.yaml` idéntico al bloque de docs/03-modelo-datos.md §4.
- [ ] `uv run pytest tests/unit tests/architecture` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
