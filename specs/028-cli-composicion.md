# 028 - Entrada: CLI y composition root

## Objetivo
Implementar la CLI `lector` (argparse) y el composition root que construye adaptadores reales a partir
de la configuración, aplicando umask, logging, guardia de red, purga automática y códigos de salida.

## Depende de
006, 007, 008, 010, 011, 012, 013, 014, 015, 016, 017, 018, 019, 020, 021, 022, 024, 025, 026, 027.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 regla 4 (inyección manual solo aquí), §6 (único `except Exception` permitido en `cli/main.py`).
- docs/02-contratos.md §7 (tabla de códigos de salida).
- reglas-seguridad.md SEG-03 (purga al inicio de todo comando que abre la BD), SEG-04 (`os.umask(0o077)` primero),
  SEG-12/13 (validación de entrada y rutas), SEG-20 (`block_network()` salvo `models fetch`), SEG-26.

## Archivos a crear/modificar
- `src/lector_placas/cli/main.py`
- `src/lector_placas/cli/commands.py`
- `src/lector_placas/cli/composition.py`
- `tests/unit/cli/__init__.py`
- `tests/unit/cli/test_cli.py`
- `tests/integration/test_cli_end_to_end.py`

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Firmas usadas (copiadas de sus specs):
```python
load_config(path: Path) -> AppConfig                                   # 006; AppConfig.under_root, .profile(name) -> (str, ProfileConfig),
                                                                       #      .plate_catalog(), .confusion_map(), .consolidation_policy(profile)
validate_video_path(path, allowed_dirs, allowed_extensions, max_size_bytes) -> Path   # 007
sha256_file(path: Path) -> str                                         # 007
resolve_within(base: Path, candidate: Path) -> Path; ensure_private_dir(path: Path) -> Path   # 007
KeyringKeyProvider(create_if_missing: bool)                            # 008
PyAVVideoSourceFactory()                                               # 010
create_session(model_path: Path, execution_provider: Literal["cuda", "cpu"]); providers_for(ep) -> list[str]   # 011
YoloEnd2EndOnnxModel(session, input_size: int)                         # 012
YoloVehicleDetector(model, score_threshold: float)                     # 013
create_oim_plate_detector(model_path: Path, score_threshold: float, providers: list[str])   # 014
YoloPlateDetector(model, score_threshold: float)                       # 015
BotSortTracker(TrackerSettings(lost_track_buffer, frame_rate, track_activation_threshold, minimum_consecutive_frames,
    minimum_iou_threshold_first_assoc, minimum_iou_threshold_second_assoc, minimum_iou_threshold_unconfirmed_assoc,
    high_conf_det_threshold, cmc_method, cmc_downscale))               # 016
create_fast_plate_ocr_reader(onnx_model_path: Path, plate_config_path: Path, providers: list[str])   # 017
LaplacianQualityScorer()                                               # 018
ManifestModelRegistry(manifest_path: Path, models_dir: Path); load_manifest(path) -> ModelManifest;
    PENDING_EXPORT; fetch_models(manifest_path, models_dir, opener) -> list[str]; default_opener   # 019
network_guard.block_network() -> None                                  # 019
SqlCipherPlateRepository(db_path: Path, key_provider: KeyProvider)     # 020
EncryptedFileCropStore(root: Path, key_provider: KeyProvider)          # 021
configure_logging(level: str, log_file: Path) -> None                  # 022
TimeBasedFrameSampler(target_fps: float)                               # 009
ProcessVideo(deps: PipelineDependencies, settings: ProcessingSettings).execute(video_path, sha) -> RunResult   # 024
PurgeExpiredData(repository, crop_store, export_store, clock, RetentionPolicy(crops_days, records_days)).execute() -> PurgeResult   # 025
ExportSightings(repository, export_store, clock).execute(status) -> Path; CsvExportStore(root: Path)   # 026
ReviewSightings(repository, crop_store, ui, clock).execute(limit) -> ReviewSummary; OpenCvReviewUI()   # 027
VotingPlateConsolidator(catalog, policy, confusions)                   # 004
SystemClock()                                                          # 005
```
```python
# cli/main.py — a implementar
def build_parser() -> argparse.ArgumentParser: ...
def exit_code_for(error: BaseException) -> int: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# cli/commands.py — a implementar (cada uno devuelve el código de salida 0)
def cmd_key_init(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_models_fetch(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_models_verify(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_process(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_review(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_export(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_purge(args: argparse.Namespace, config: AppConfig) -> int: ...

# cli/composition.py — a implementar
def data_dir(config: AppConfig) -> Path: ...
def build_key_provider(create_if_missing: bool) -> KeyProvider: ...
def build_repository(config: AppConfig, keys: KeyProvider) -> SqlCipherPlateRepository: ...
def build_crop_store(config: AppConfig, keys: KeyProvider) -> EncryptedFileCropStore: ...
def build_export_store(config: AppConfig) -> CsvExportStore: ...
def build_registry(config: AppConfig) -> ManifestModelRegistry: ...
def build_purge(config: AppConfig, repository: PlateRepository, crop_store: CropStore,
                export_store: ExportStore, clock: Clock) -> PurgeExpiredData: ...
def build_vehicle_detector(config: AppConfig, registry: ModelRegistry) -> VehicleDetector: ...
def build_plate_detector(config: AppConfig, registry: ModelRegistry) -> PlateDetector: ...
def build_reader(config: AppConfig, registry: ModelRegistry) -> PlateReader: ...
def build_tracker(config: AppConfig, profile: ProfileConfig) -> Tracker: ...
def build_process_video(config: AppConfig, profile_name: str, repository: PlateRepository,
                        crop_store: CropStore, clock: Clock) -> ProcessVideo: ...
```

## Comportamiento esperado
1. **Parser** (`prog="lector"`): opción global `--config` (tipo `Path`, por defecto `Path("config/lector.yaml")`).
   Subcomandos (cada uno fija `handler=<cmd_*>` y `network=<bool>` con `set_defaults`):
   - `key init` → `cmd_key_init`; `models fetch` → `cmd_models_fetch` (`network=True`); `models verify` → `cmd_models_verify`;
   - `process VIDEO [--profile NOMBRE]` (`VIDEO` tipo `Path`);
   - `review [--limit N]` (int, por defecto 50);
   - `export [--status {confirmed,unverified,rejected,corrected}]`;
   - `purge`.
   Todos menos `models fetch` tienen `network=False`. Subcomando obligatorio.
2. **`exit_code_for`**: tabla de docs/02-contratos.md §7, evaluada con `isinstance` en este orden:
   `ConfigurationError`→2; `InputValidationError`/`VideoSourceError`→3; `ModelIntegrityError`/`ModelLoadError`/`ModelFetchError`→4;
   `KeyUnavailableError`/`EncryptionError`→5; `RepositoryError`/`CropStoreError`/`ExportError`→6; `NetworkAccessError`→7; `EvaluationError`/`DatasetError`→8; otro→1.
3. **`main(argv)`**: primera instrucción `os.umask(0o077)`; `args = build_parser().parse_args(argv)`; luego:
   `config = load_config(args.config)`; `configure_logging(config.logging.level, config.under_root(config.paths.log_dir) / "lector.log")`;
   si `not args.network` → `network_guard.block_network()` (llamado vía el módulo `network_guard`, para poder sustituirlo en tests);
   `return args.handler(args, config)`.
   `LectorPlacasError` → `logger.error("comando fallido error=%s", type(e).__name__)`, `sys.stderr.write(f"error: {e}\n")`, `return exit_code_for(e)`.
   `Exception` → `logger.exception("error inesperado")`, `sys.stderr.write("error inesperado; revise logs/lector.log\n")`, `return 1`
   (con `# noqa: BLE001` y comentario "último nivel, ARQUITECTURA §6").
4. **Comandos** (`commands.py` llama a la composición siempre como `composition.<función>(...)`, importando el módulo
   `from lector_placas.cli import composition`, para que los tests puedan sustituir funciones):
   - `cmd_key_init`: `composition.build_key_provider(True).master_key()`; escribe `"clave maestra disponible en el keyring\n"` en `sys.stdout`.
   - `cmd_models_fetch`: `fetch_models(manifest, models_dir, default_opener)`; escribe `f"descargados: {', '.join(ids) or 'ninguno'}\n"`.
   - `cmd_models_verify`: carga el manifiesto; para cada entrada: si `sha256 == PENDING_EXPORT` escribe `f"{id}: pendiente de exportar\n"`;
     si no `registry.verified_path(id)` (propaga `ModelIntegrityError`) y escribe `f"{id}: ok\n"`.
   - Comandos con BD (`process`, `review`, `export`, `purge`): `keys = composition.build_key_provider(False)`, `clock = SystemClock()`,
     `repository = composition.build_repository(config, keys)`; en `try/finally` con `repository.close()`:
     `crops = composition.build_crop_store(config, keys)`, `exports = composition.build_export_store(config)`,
     **purga primero** `composition.build_purge(config, repository, crops, exports, clock).execute()`, luego la acción.
   - `cmd_process`: **antes de abrir la BD**: `name, profile = config.profile(args.profile)`;
     `video = validate_video_path(args.video, [config.under_root(d) for d in config.input.allowed_dirs], frozenset(config.input.allowed_extensions), config.input.max_file_size_mb * 1024 * 1024)`;
     `sha = sha256_file(video)`. Tras la purga: `result = composition.build_process_video(config, name, repository, crops, clock).execute(video, sha)`;
     escribe `f"run_id={result.run_id} frames={s.frames_processed}/{s.frames_decoded} confirmadas={s.sightings_confirmed} sin_verificar={s.sightings_unverified} sin_lectura={s.tracks_without_reading} velocidad={vel}\n"`
     con `vel = f"{s.speed_factor:.2f}x"` o `"n/d"`.
   - `cmd_review`: `ReviewSightings(repository, crops, OpenCvReviewUI(), clock).execute(args.limit)`; escribe los cuatro conteos.
   - `cmd_export`: `ExportSightings(repository, exports, clock).execute(ReviewStatus(args.status) if args.status else None)`; escribe `f"exportado: {path.name}\n"`.
   - `cmd_purge`: la purga inicial es la acción; escribe sus conteos (`recortes=`, `avistamientos=`, `corridas=`, `placas=`, `exportaciones=`).
5. **Composición**:
   - `data_dir(config)` = `ensure_private_dir(config.under_root(config.paths.data_dir))`.
   - `build_repository` → `SqlCipherPlateRepository(resolve_within(data_dir(config), Path("lector.db")), keys)`;
     `build_crop_store` → `EncryptedFileCropStore(resolve_within(data_dir(config), Path("crops")), keys)`;
     `build_export_store` → `CsvExportStore(resolve_within(data_dir(config), Path("exports")))`.
   - `build_registry` → `ManifestModelRegistry(config.under_root(config.paths.model_manifest), config.under_root(config.paths.models_dir))`.
   - `build_purge` → `PurgeExpiredData(..., RetentionPolicy(config.retention.crops_days, config.retention.records_days))`.
   - `build_vehicle_detector`: `ep = config.inference.execution_provider`; `vd = config.models.vehicle_detector`;
     `YoloVehicleDetector(YoloEnd2EndOnnxModel(create_session(registry.verified_path(vd.model_id), ep), vd.input_size), vd.score_threshold)`.
   - `build_plate_detector`: `pd = config.models.plate_detector`; backend `open_image_models` →
     `create_oim_plate_detector(registry.verified_path(pd.model_id), pd.score_threshold, providers_for(ep))`;
     backend `yolo` → `YoloPlateDetector(YoloEnd2EndOnnxModel(create_session(registry.verified_path(pd.model_id), ep), pd.input_size), pd.score_threshold)`.
   - `build_reader` → `create_fast_plate_ocr_reader(registry.verified_path(ocr.model_id), registry.verified_path(ocr.config_id), providers_for(ep))`.
   - `build_tracker(config, profile)` → `BotSortTracker(TrackerSettings(**campos de config.tracker, frame_rate=profile.target_fps))` (campos explícitos, sin `**` sobre el modelo pydantic).
   - `build_process_video`: `name, profile = config.profile(profile_name)`; `registry = build_registry(config)`;
     `deps = PipelineDependencies(PyAVVideoSourceFactory(), TimeBasedFrameSampler(profile.target_fps), build_vehicle_detector(...),
     build_plate_detector(...), build_tracker(config, profile), build_reader(...), LaplacianQualityScorer(),
     VotingPlateConsolidator(config.plate_catalog(), config.consolidation_policy(profile), config.confusion_map()),
     repository, crop_store, clock)`; `settings = ProcessingSettings(name, profile.max_ocr_per_frame, profile.min_plate_width_px,
     profile.min_sharpness, profile.vehicle_crop_margin, profile.track_finalize_after_ms, profile.max_readings_per_track)`.

## Casos borde y manejo de errores
- `print` solo en `cli/` y únicamente a través de `sys.stdout.write`/`sys.stderr.write` como se indica.
- La salida de consola nunca incluye texto de placa (solo conteos y nombres de archivo).

## Tests de aceptación
```python
# tests/unit/cli/test_cli.py
from __future__ import annotations

from pathlib import Path

import pytest

from lector_placas.cli.main import build_parser, exit_code_for
from lector_placas.domain.errors import (
    ConfigurationError, CropStoreError, DatasetError, EncryptionError, EvaluationError, ExportError,
    InputValidationError,
    KeyUnavailableError, LectorPlacasError, ModelFetchError, ModelIntegrityError, NetworkAccessError,
    RepositoryError, UnsafePathError, VideoSourceError,
)


def test_parser_process() -> None:
    args = build_parser().parse_args(["--config", "c.yaml", "process", "v.mp4", "--profile", "parqueadero"])
    assert (args.config, args.video, args.profile, args.network) == (
        Path("c.yaml"), Path("v.mp4"), "parqueadero", False)


def test_parser_defaults_and_network_flag() -> None:
    parser = build_parser()
    assert parser.parse_args(["review"]).limit == 50
    assert parser.parse_args(["purge"]).config == Path("config/lector.yaml")
    assert parser.parse_args(["models", "fetch"]).network is True
    assert parser.parse_args(["models", "verify"]).network is False
    assert parser.parse_args(["export", "--status", "unverified"]).status == "unverified"
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.parametrize("error,code", [
    (ConfigurationError("x"), 2), (InputValidationError("x"), 3), (UnsafePathError("x"), 3),
    (VideoSourceError("x"), 3), (ModelIntegrityError("x"), 4), (ModelFetchError("x"), 4),
    (KeyUnavailableError("x"), 5), (EncryptionError("x"), 5), (RepositoryError("x"), 6),
    (CropStoreError("x"), 6), (ExportError("x"), 6), (NetworkAccessError("x"), 7), (EvaluationError("x"), 8),
    (DatasetError("x"), 8),
    (LectorPlacasError("x"), 1), (RuntimeError("x"), 1),
])
def test_exit_codes(error: BaseException, code: int) -> None:
    assert exit_code_for(error) == code
```
```python
# tests/integration/test_cli_end_to_end.py
from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from lector_placas.cli import composition, main as cli_main
from lector_placas.infrastructure import network_guard
from tests.fixtures.fakes import FakeKeyProvider
from tests.fixtures.synthetic_video import write_video

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    (tmp_path / "videos").mkdir()
    monkeypatch.setattr(composition, "build_key_provider", lambda create_if_missing: FakeKeyProvider())
    monkeypatch.setattr(network_guard, "block_network", lambda: None)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    return tmp_path


def run(project: Path, *args: str) -> int:
    return cli_main.main(["--config", str(project / "config" / "lector.yaml"), *args])


def test_purge_and_export_create_private_files(project: Path) -> None:
    assert run(project, "purge") == 0
    database = project / "data" / "lector.db"
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert run(project, "export") == 0
    exported = list((project / "data" / "exports").glob("sightings-*.csv"))
    assert len(exported) == 1
    assert (project / "logs" / "lector.log").exists()


def test_error_exit_codes(project: Path) -> None:
    assert run(project, "process", str(project / "videos" / "no-existe.mp4")) == 3
    outside = write_video(project / "fuera.mp4", frames=2)
    assert run(project, "process", str(outside)) == 3
    assert run(project, "models", "verify") == 4
    assert cli_main.main(["--config", str(project / "config" / "no.yaml"), "purge"]) == 2


@pytest.mark.gpu
@pytest.mark.skipif(not (MODELS / "yolo26n-coco").exists(), reason="modelos no disponibles")
def test_process_synthetic_video_end_to_end(project: Path) -> None:
    shutil.copytree(MODELS, project / "models")
    shutil.copy(ROOT / "config" / "models.yaml", project / "config" / "models.yaml")
    video = write_video(project / "videos" / "sintetico.mp4", frames=20, width=320, height=240)
    assert run(project, "process", str(video)) == 0
```

## Fuera de alcance
Comandos de evaluación (spec 029) y de datasets (spec 031).

## Definition of Done
- [ ] `uv run pytest tests/unit/cli tests/architecture` y `uv run pytest -m integration tests/integration/test_cli_end_to_end.py` en verde.
- [ ] Con modelos descargados/exportados: `uv run pytest -m gpu tests/integration/test_cli_end_to_end.py` en verde.
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` limpios.
- [ ] `uv run lector --help` muestra los subcomandos.
