# 035 - Exportar lecturas revisadas para reentrenar el OCR (con retención propia)

## Objetivo
Añadir `lector dataset export-reviewed`, que exporta los recortes de avistamientos `confirmed` y `corrected` en el
formato de fast-plate-ocr, y hacer que la purga los borre a los `retention.training_days` días (180 por defecto).

## Depende de
006, 021, 025, 026, 028, 031.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-07 (excepción controlada para esta exportación), SEG-03 (retención `training_days`),
  SEG-04 (0700/0600), SEG-05 (auditoría y consola sin texto de placa), SEG-13 (`resolve_within`).
- docs/02-contratos.md §4 (`TrainingExportStore`) y §5 (`ExportReviewedCrops`, cambios en la purga).
- docs/03-modelo-datos.md §4 (`retention.training_days`). ADR-005 (actualización 2026-09-26).

## Archivos a crear/modificar
- `src/lector_placas/application/ports.py` (añadir `TrainingExportStore`)
- `src/lector_placas/application/export_reviewed.py` (nuevo)
- `src/lector_placas/application/purge_expired.py` (retención de entrenamiento)
- `src/lector_placas/adapters/export/training_export_store.py` (nuevo)
- `src/lector_placas/infrastructure/config.py` (`RetentionConfig.training_days`)
- `config/lector.yaml` (`retention.training_days: 180`)
- `src/lector_placas/cli/composition.py` (`build_training_store`, `build_purge`)
- `src/lector_placas/cli/dataset_commands.py` (subcomando `export-reviewed`)
- `tests/unit/application/test_export_reviewed.py` (nuevo)
- `tests/unit/application/test_purge_training.py` (nuevo)
- `tests/unit/adapters/test_training_export_store.py` (nuevo)
- `tests/unit/cli/test_export_reviewed_cli.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
```python
# application/ports.py — existentes (sin cambios)
ImageBGR: TypeAlias = npt.NDArray[np.uint8]
class AuditEvent(StrEnum): ... EXPORT = "export"
class PlateRepository(Protocol):
    def list_sightings(self, status: ReviewStatus | None, limit: int, offset: int) -> list[SightingRecord]: ...
    def log_event(self, event: AuditEvent, occurred_at: datetime, detail: str) -> None: ...
class CropStore(Protocol):
    def load(self, crop_ref: str) -> ImageBGR: ...    # CropNotFoundError si no existe
class Clock(Protocol):
    def now(self) -> datetime: ...
# nuevo en ports.py (tras ExportStore)
class TrainingExportStore(Protocol):
    def write_samples(self, samples: Sequence[tuple[str, ImageBGR]], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...
```
```python
# application/export_reviewed.py — nuevo
PAGE_SIZE: Final[int] = 500
EXPORTED_STATUSES: Final[tuple[ReviewStatus, ...]] = (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED)

@dataclass(frozen=True, slots=True)
class ExportReviewedResult:
    path: Path
    exported: int
    skipped: int

class ExportReviewedCrops:
    def __init__(self, repository: PlateRepository, crop_store: CropStore,
                 training_store: TrainingExportStore, clock: Clock) -> None: ...
    def execute(self) -> ExportReviewedResult: ...

# application/purge_expired.py — cambios
@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    crops_days: int
    records_days: int
    training_days: int = 180          # nuevo; >= 1

@dataclass(frozen=True, slots=True)
class PurgeResult:
    crops_deleted: int
    sightings_deleted: int
    runs_deleted: int
    plates_deleted: int
    exports_deleted: int
    training_deleted: int = 0          # nuevo

class PurgeExpiredData:
    def __init__(self, repository: PlateRepository, crop_store: CropStore, export_store: ExportStore,
                 clock: Clock, policy: RetentionPolicy,
                 training_store: TrainingExportStore | None = None) -> None: ...   # nuevo parámetro opcional

# adapters/export/training_export_store.py — nuevo
DIR_PREFIX: Final[str] = "reviewed-"
ANNOTATIONS_FILE: Final[str] = "annotations.csv"
IMAGES_DIR: Final[str] = "images"

class FilesystemTrainingExportStore:
    def __init__(self, root: Path) -> None: ...
    def write_samples(self, samples: Sequence[tuple[str, ImageBGR]], created_at: datetime) -> Path: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...

# cli/composition.py — nuevo
TRAINING_EXPORT_DIR: Final[Path] = Path("training/ocr/datasets/own")
def build_training_store(config: AppConfig) -> FilesystemTrainingExportStore: ...

# cli/dataset_commands.py — nuevo
def cmd_export_reviewed(args: argparse.Namespace, config: AppConfig) -> int: ...
```

## Comportamiento esperado
1. `RetentionPolicy.__post_init__` añade: `training_days >= 1`, si no `ConfigurationError`.
2. `PurgeExpiredData.execute()`: tras borrar exportaciones CSV, si `training_store` no es `None`:
   `training_deleted = training_store.delete_older_than(now - timedelta(days=policy.training_days))`; si es `None`, 0.
   `PurgeResult(..., training_deleted=...)`; el `detail` de auditoría y el log añaden `f" entrenamiento={training_deleted}"`
   al final. El resto del orden y comportamiento no cambia.
3. `ExportReviewedCrops.execute()`:
   - `now = clock.now()`. Para cada estado de `EXPORTED_STATUSES` (en ese orden) pagina
     `repository.list_sightings(estado, PAGE_SIZE, offset)` hasta recibir menos de `PAGE_SIZE`.
   - Por registro: `crop_ref is None` → `skipped += 1`; si no, `crop_store.load(crop_ref)`; `CropNotFoundError` →
     `skipped += 1`; si carga, añade `(record.plate_text, imagen)` a las muestras.
   - `path = training_store.write_samples(muestras, now)`;
     `repository.log_event(AuditEvent.EXPORT, now, f"entrenamiento filas={len(muestras)} omitidos={skipped} carpeta={path.name}")`;
     `logger.info` con los mismos conteos (sin placas). Devuelve `ExportReviewedResult(path, len(muestras), skipped)`.
4. `FilesystemTrainingExportStore`:
   - `write_samples(samples, created_at)`: cada texto debe cumplir `PLATE_TEXT_REGEX`, si no `ExportError("texto de placa inválido")`.
     `ensure_private_dir(root)`; `name = f"{DIR_PREFIX}{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}"`;
     `target = resolve_within(root, Path(name))`; si existe → `ExportError("ya existe una exportación con ese nombre")`.
     `ensure_private_dir(target)` y `ensure_private_dir(target / IMAGES_DIR)`. Por muestra `i`: `cv2.imencode(".png", imagen)`
     (fallo → `ExportError`) y escritura con `os.open(ruta, O_WRONLY | O_CREAT | O_EXCL, 0o600)` en
     `images/{i:06d}.png`. `annotations.csv` (0600, `O_EXCL`, UTF-8, `lineterminator="\n"`) con cabecera
     `image_path,plate_text` y filas `images/{i:06d}.png,<texto>`. `OSError` → `ExportError`. Devuelve `target`.
   - `delete_older_than(cutoff)`: si `root` no existe → 0. Borra con `shutil.rmtree` cada directorio `root.glob(f"{DIR_PREFIX}*")`
     con `stat().st_mtime < cutoff.timestamp()`; devuelve cuántos. `OSError` → `ExportError`.
5. Config: `RetentionConfig.training_days: int`; en el `model_validator` de `AppConfig` exige `1 <= training_days <= 3650`.
   `config/lector.yaml` añade `training_days: 180` bajo `retention` (después de `records_days`).
6. Composición: `build_training_store(config)` → `FilesystemTrainingExportStore(resolve_within(config.root_dir, TRAINING_EXPORT_DIR))`.
   `build_purge` pasa `RetentionPolicy(crops_days, records_days, config.retention.training_days)` y
   `training_store=build_training_store(config)`.
7. CLI: en `register_dataset_commands`, subcomando `dataset export-reviewed` sin argumentos, con
   `set_defaults(handler=cmd_export_reviewed, network=False, key="load")`. `cmd_export_reviewed` usa
   `commands._run_with_repository(config, commands.require_keys(args), action)`; la acción ejecuta
   `ExportReviewedCrops(repository, crop_store, composition.build_training_store(config), clock).execute()` y escribe
   `f"exportados={r.exported} omitidos={r.skipped} carpeta={r.path.name}\n"` en `sys.stdout`. Devuelve 0.

## Casos borde y manejo de errores
- Exportar sin lecturas revisadas crea una carpeta con `annotations.csv` solo con cabecera.
- Ni la consola, ni los logs, ni `audit_log` contienen texto de placa (solo conteos y nombre de carpeta).

## Tests de aceptación
```python
# tests/unit/application/test_export_reviewed.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from lector_placas.application.export_reviewed import ExportReviewedCrops
from lector_placas.application.ports import AuditEvent, ImageBGR, RunStart, VideoInfo
from lector_placas.domain.entities import (
    ConsolidatedPlate, ReviewStatus, Sighting, UnverifiedReason, VehicleType,
)
from tests.fixtures.fakes import START, FakeClock, InMemoryCropStore, InMemoryPlateRepository


class FakeTrainingStore:
    def __init__(self) -> None:
        self.samples: list[tuple[str, ImageBGR]] = []

    def write_samples(self, samples, created_at: datetime) -> Path:  # type: ignore[no-untyped-def]
        self.samples = list(samples)
        return Path("reviewed-20260926T120000Z")

    def delete_older_than(self, cutoff: datetime) -> int:
        return 0


def confirmed(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(text, 0.95, 1.0, 3, ReviewStatus.CONFIRMED, (), ())


def unverified(text: str) -> ConsolidatedPlate:
    return ConsolidatedPlate(text, 0.4, 0.5, 2, ReviewStatus.UNVERIFIED,
                             (UnverifiedReason.LOW_CONFIDENCE,), ())


def test_exports_confirmed_and_corrected_only() -> None:
    repo, crops = InMemoryPlateRepository(), InMemoryCropStore()
    run_id = repo.start_run(RunStart("a" * 64, "p", VideoInfo(1, 1, 0, None, None, "x"), START))

    def add(track: int, plate: ConsolidatedPlate, crop_ref: str | None) -> int:
        return repo.save_sighting(
            Sighting(run_id, track, 0, 1, VehicleType.CAR, plate, crop_ref, START))

    add(1, confirmed("ABC123"), crops.save(np.full((10, 30, 3), 1, np.uint8)))
    corrected_id = add(2, unverified("XYZ98K"), crops.save(np.full((10, 30, 3), 2, np.uint8)))
    repo.record_review(corrected_id, ReviewStatus.CORRECTED, "XYZ98L", START)
    add(3, unverified("DEF456"), crops.save(np.full((10, 30, 3), 3, np.uint8)))
    add(4, confirmed("GHI789"), "f" * 32)
    add(5, confirmed("JKL012"), None)

    store = FakeTrainingStore()
    result = ExportReviewedCrops(repo, crops, store, FakeClock()).execute()

    assert [text for text, _ in store.samples] == ["ABC123", "XYZ98L"]
    assert [int(image[0, 0, 0]) for _, image in store.samples] == [1, 2]
    assert (result.exported, result.skipped, result.path.name) == (2, 2, "reviewed-20260926T120000Z")
    event, _, detail = repo.events[-1]
    assert event is AuditEvent.EXPORT
    assert "filas=2" in detail and "omitidos=2" in detail
    assert "ABC" not in detail and "XYZ" not in detail
```
```python
# tests/unit/application/test_purge_training.py
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lector_placas.application.purge_expired import PurgeExpiredData, RetentionPolicy
from lector_placas.domain.errors import ConfigurationError
from tests.fixtures.fakes import (
    START, FakeClock, InMemoryCropStore, InMemoryExportStore, InMemoryPlateRepository,
)


class FakeTrainingStore:
    def __init__(self, deleted: int) -> None:
        self.deleted = deleted
        self.cutoffs: list[datetime] = []

    def write_samples(self, samples, created_at: datetime) -> Path:  # type: ignore[no-untyped-def]
        return Path("x")

    def delete_older_than(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return self.deleted


def purge(store: FakeTrainingStore | None, policy: RetentionPolicy) -> PurgeExpiredData:
    return PurgeExpiredData(InMemoryPlateRepository(), InMemoryCropStore(), InMemoryExportStore(),
                            FakeClock(), policy, training_store=store)


def test_purge_deletes_expired_training_exports() -> None:
    store = FakeTrainingStore(3)
    use_case = purge(store, RetentionPolicy(30, 90, 180))
    result = use_case.execute()
    assert result.training_deleted == 3
    assert store.cutoffs == [START - timedelta(days=180)]


def test_purge_without_training_store_and_default_policy() -> None:
    assert purge(None, RetentionPolicy(30, 90)).execute().training_deleted == 0
    assert RetentionPolicy(30, 90).training_days == 180


def test_invalid_training_days() -> None:
    with pytest.raises(ConfigurationError):
        RetentionPolicy(30, 90, 0)


def test_audit_detail_includes_training_count() -> None:
    repo = InMemoryPlateRepository()
    PurgeExpiredData(repo, InMemoryCropStore(), InMemoryExportStore(), FakeClock(),
                     RetentionPolicy(30, 90), training_store=FakeTrainingStore(2)).execute()
    assert repo.events[-1][2].endswith("entrenamiento=2")
```
```python
# tests/unit/adapters/test_training_export_store.py
from __future__ import annotations

import csv
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from lector_placas.adapters.export.training_export_store import FilesystemTrainingExportStore
from lector_placas.domain.errors import ExportError

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def image() -> np.ndarray:
    img = np.zeros((10, 30, 3), np.uint8)
    img[:, :, 2] = 200
    return img


def test_write_samples_creates_private_dataset(tmp_path: Path) -> None:
    store = FilesystemTrainingExportStore(tmp_path / "own")
    path = store.write_samples([("ABC123", image()), ("XYZ98K", image())], T0)
    assert path.name == "reviewed-20260926T120000Z"
    rows = list(csv.DictReader((path / "annotations.csv").open(encoding="utf-8")))
    assert rows == [
        {"image_path": "images/000000.png", "plate_text": "ABC123"},
        {"image_path": "images/000001.png", "plate_text": "XYZ98K"},
    ]
    np.testing.assert_array_equal(cv2.imread(str(path / "images" / "000000.png")), image())
    for file in (path / "annotations.csv", path / "images" / "000001.png"):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    for directory in (tmp_path / "own", path, path / "images"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    with pytest.raises(ExportError):
        store.write_samples([], T0)


def test_rejects_invalid_plate_text(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        FilesystemTrainingExportStore(tmp_path / "own").write_samples([("abc", image())], T0)


def test_delete_older_than(tmp_path: Path) -> None:
    store = FilesystemTrainingExportStore(tmp_path / "own")
    assert store.delete_older_than(T0) == 0
    old = store.write_samples([("ABC123", image())], T0)
    new = store.write_samples([("ABC123", image())], T0 + timedelta(seconds=1))
    past = (datetime.now(UTC) - timedelta(days=200)).timestamp()
    os.utime(old, (past, past))
    assert store.delete_older_than(datetime.now(UTC) - timedelta(days=180)) == 1
    assert not old.exists() and new.exists()
```
```python
# tests/unit/cli/test_export_reviewed_cli.py
from __future__ import annotations

from pathlib import Path

from lector_placas.cli.main import build_parser
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]


def test_parser_registers_export_reviewed() -> None:
    args = build_parser().parse_args(["dataset", "export-reviewed"])
    assert (args.key, args.network) == ("load", False)


def test_config_has_training_retention() -> None:
    assert load_config(ROOT / "config" / "lector.yaml").retention.training_days == 180
```

## Fuera de alcance
Unir estos CSV con los de otras fuentes para entrenar (se hará al preparar el Paso 5).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] Ningún `print`/log/auditoría con texto de placa (`grep` del checklist de reglas-seguridad.md §8).
