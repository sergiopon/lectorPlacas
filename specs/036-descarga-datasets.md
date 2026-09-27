# 036 - Descarga automática de datasets (Roboflow) y preparación en un paso

## Objetivo
`lector dataset download` descarga los datasets públicos de Roboflow listados en `config/datasets.yaml` usando la API
REST verificada, y `lector dataset prepare` encadena descarga → `merge-detection` → `chars-to-ocr` sin trabajo manual.

## Depende de
007, 019, 028, 031.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-20/SEG-21 (excepción de red para estos dos comandos; API key solo en `ROBOFLOW_API_KEY`),
  SEG-13 (rutas y protección contra *zip slip*), SEG-14 (`yaml.safe_load`), SEG-25/26 (la clave nunca en logs ni errores).
- ADR-012 (actualización 2026-09-26). docs/04-evaluacion.md §5.1 (fuentes y licencias).

## API REST verificada (código del SDK `roboflow` 1.5.1, `roboflow/adapters/rfapi.py` y `core/version.py`)
- Proyecto: `GET https://api.roboflow.com/{workspace}/{project}?api_key={KEY}` → 200 con JSON que contiene `"versions"`
  (lista de objetos con `"id"`; el número de versión es el último segmento de `id` separado por `/`).
- Exportación: `GET https://api.roboflow.com/{workspace}/{project}/{version}/{format}?api_key={KEY}&nocache=true` →
  **202** mientras se genera (JSON con `"progress"`), **200** cuando está lista con `payload["export"]["link"]`.
- Descarga: `GET {link}` → zip. Formato usado: `yolov8`.
- VERIFICADO (2026-09-26, respuesta real de la API): `"id"` tiene la forma `<workspace>/<project>/<n>` (p. ej.
  `usco-thj9e/placas-colombia-ixdpr/4`); las versiones no vienen ordenadas, por eso se toma el máximo. Un proyecto sin
  versión generada devuelve `"versions": []` (y `project.versions: 0`) y no se puede exportar: se detiene con
  `DatasetError("sin versiones generadas: <workspace>/<project>")`. Si el último segmento no es un entero, con
  `DatasetError("formato de versiones inesperado: <workspace>/<project>")`.

## Archivos a crear/modificar
- `config/datasets.yaml` (nuevo, contenido literal abajo)
- `src/lector_placas/datasets/registry.py` (nuevo)
- `src/lector_placas/infrastructure/dataset_fetcher.py` (nuevo; único módulo nuevo con red)
- `src/lector_placas/cli/dataset_download_commands.py` (nuevo)
- `src/lector_placas/cli/dataset_commands.py` (registrar los subcomandos nuevos)
- `tests/unit/datasets/test_registry.py` (nuevo)
- `tests/unit/infrastructure/test_dataset_fetcher.py` (nuevo)
- `tests/unit/cli/test_dataset_download_cli.py` (nuevo)

## Dependencias externas
Ninguna nueva (stdlib `urllib`, `zipfile`, `json`, `time`; pydantic y PyYAML ya instalados). **Prohibido** añadir el
paquete `roboflow` (exige `numpy<2.4` y `opencv-python-headless`).

## Interfaces y tipos involucrados
```python
# existentes
def resolve_within(base: Path, candidate: Path) -> Path: ...        # infrastructure/paths.py; UnsafePathError
def ensure_private_dir(path: Path) -> Path: ...                     # infrastructure/paths.py
def read_class_names(data_yaml: Path) -> dict[int, str]: ...        # datasets/yolo_format.py
def merge_detection(sources_file: Path, raw_root: Path, output_dir: Path) -> MergeSummary: ...   # datasets/merge_detection.py
def chars_to_ocr(source_dir: Path, output_dir: Path, catalog: PlateFormatCatalog) -> OcrSummary: ...  # datasets/chars_to_ocr.py
class DatasetError(LectorPlacasError): ...
class ConfigurationError(LectorPlacasError): ...
# cli/dataset_commands.py (existentes)
DETECTOR_ROOT: Final[Path] = Path("training/detector")
OCR_DATASETS_ROOT: Final[Path] = Path("training/ocr/datasets")
RAW_DIR: Final[str] = "raw"
```
```python
# datasets/registry.py — nuevo
AUTO: Final[str] = "auto"

class DatasetEntry(BaseModel):                 # extra="forbid", frozen=True
    name: str                                   # ^[a-z0-9_-]{1,40}$
    workspace: str                              # ^[a-z0-9_-]{1,100}$
    project: str                                # ^[a-z0-9_-]{1,100}$
    target: Literal["detector", "ocr"]
    plate_classes: str | tuple[str, ...] = AUTO # "auto" o lista no vacía; solo se usa con target "detector"
    license: str                                # no vacío

class DatasetRegistry(BaseModel):              # extra="forbid", frozen=True
    version: Literal[1]
    format: Literal["yolov8"]
    datasets: tuple[DatasetEntry, ...]          # >= 1, nombres únicos

def load_registry(path: Path) -> DatasetRegistry: ...
def resolve_plate_classes(entry: DatasetEntry, dataset_dir: Path) -> tuple[str, ...]: ...
def write_sources_file(registry: DatasetRegistry, raw_root: Path, path: Path) -> int: ...

# infrastructure/dataset_fetcher.py — nuevo
API_URL: Final[str] = "https://api.roboflow.com"
ENV_API_KEY: Final[str] = "ROBOFLOW_API_KEY"
POLL_SECONDS: Final[float] = 2.0
MAX_POLLS: Final[int] = 150
TIMEOUT_SECONDS: Final[float] = 60.0
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 600.0

class HttpGet(Protocol):
    def __call__(self, url: str, timeout: float) -> tuple[int, bytes]: ...

def default_http_get(url: str, timeout: float) -> tuple[int, bytes]: ...
def api_key_from_env(environ: Mapping[str, str]) -> str: ...
def latest_version(http_get: HttpGet, api_key: str, workspace: str, project: str) -> int: ...
def export_link(http_get: HttpGet, api_key: str, workspace: str, project: str, version: int,
                fmt: str, sleep: Callable[[float], None]) -> str: ...
def extract_zip(data: bytes, destination: Path) -> None: ...
def download_dataset(http_get: HttpGet, api_key: str, workspace: str, project: str, fmt: str,
                     destination: Path, sleep: Callable[[float], None]) -> int: ...

# cli/dataset_download_commands.py — nuevo
REGISTRY_FILE: Final[Path] = Path("config/datasets.yaml")
SOURCES_FILE: Final[str] = "sources.yaml"
MERGED_OUTPUT: Final[str] = "merged"
OCR_OUTPUT: Final[str] = "ocr_colombia"
def register_download_commands(dataset_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...
def cmd_download(args: argparse.Namespace, config: AppConfig) -> int: ...
def cmd_prepare(args: argparse.Namespace, config: AppConfig) -> int: ...
```

## Comportamiento esperado
1. `config/datasets.yaml` **literal**:
```yaml
version: 1
format: yolov8
datasets:
  - {name: usco, workspace: usco-thj9e, project: placas-colombia-ixdpr, target: detector,
     plate_classes: [placa], license: "MIT (declarada por quien lo subió)"}
  - {name: placas_motos_carros, workspace: reimerjsuarez, project: placas_motos_carros, target: detector,
     plate_classes: [Placas], license: "CC BY 4.0"}
  - {name: motos_placas, workspace: placas-sn7fb, project: motos-placas, target: detector,
     plate_classes: [motos-placas], license: "CC BY 4.0"}   # NO VERIFICADO que motos-placas sea la clase de placa
  - {name: ocr_placas_colombia, workspace: sergio-ponce-asprilla, project: ocr-placas-colombia-etll5-lwpkc, target: ocr,
     license: "CC BY 4.0"}   # fork de ia-xgdnt/ocr-placas-colombia-etll5 (sin versiones)
```
2. `registry.py`:
   - `load_registry`: `yaml.safe_load` + validación; errores → `DatasetError("registro de datasets inválido: <detalle>")`.
   - `resolve_plate_classes(entry, dir)`: lista explícita → tal cual; `"auto"` → `read_class_names(dir / "data.yaml")` debe
     tener **exactamente una** clase (si no → `DatasetError(f"{name}: plate_classes=auto exige una sola clase; encontradas: <nombres>")`).
   - `write_sources_file(registry, raw_root, path)`: para cada entrada `detector` cuya carpeta `raw_root/<name>` exista, una
     fuente con `name`, `path: <name>`, `url: https://universe.roboflow.com/<workspace>/<project>`, `license` y las
     `plate_classes` resueltas; escribe `{"version": 1, "sources": [...]}` con `yaml.safe_dump`. Devuelve cuántas fuentes escribió
     (0 → `DatasetError("no hay datasets de detección descargados")`).
3. `dataset_fetcher.py`:
   - `default_http_get`: `urllib.request.urlopen(url, timeout=timeout)` → `(status, body)`; `urllib.error.HTTPError` →
     `(e.code, e.read())`; `URLError`/`OSError`/`TimeoutError` → `DatasetError("error de red al contactar Roboflow")`.
     **Nunca** incluye la URL (contiene la clave) en mensajes ni logs.
   - `api_key_from_env(environ)`: valor no vacío de `ROBOFLOW_API_KEY` o `ConfigurationError("defina la variable de entorno ROBOFLOW_API_KEY")`.
   - `latest_version`: GET del proyecto; status ≠ 200 → `DatasetError(f"no se pudo consultar {workspace}/{project} (HTTP {status})")`;
     `max(int(str(v["id"]).rsplit("/", 1)[-1]) for v in json["versions"])`; **lista vacía** (proyecto sin versión generada;
     Roboflow solo exporta versiones generadas) → `DatasetError(f"sin versiones generadas: {workspace}/{project}")`;
     `KeyError`/`ValueError`/`TypeError`/`json.JSONDecodeError` → `DatasetError(f"formato de versiones inesperado: {workspace}/{project}")`.
   - `export_link`: hasta `MAX_POLLS` intentos: 202 → `sleep(POLL_SECONDS)`; 200 → `json["export"]["link"]` (debe empezar por
     `https://`, si no o si falta → `DatasetError`); otro status → `DatasetError(f"exportación falló: {workspace}/{project} (HTTP {status})")`.
     Agotados los intentos → `DatasetError("la exportación no terminó a tiempo")`.
   - `extract_zip(data, destination)`: `zipfile.ZipFile(io.BytesIO(data))`; `zipfile.BadZipFile` → `DatasetError`; **antes de
     extraer**, cada miembro debe cumplir `resolve_within(destination, Path(nombre))` (zip slip → `UnsafePathError`);
     `ensure_private_dir(destination)`; luego `extractall(destination)`.
   - `download_dataset(...)`: `version = latest_version(...)`; `link = export_link(...)`; `status, body = http_get(link, DOWNLOAD_TIMEOUT_SECONDS)`
     (≠ 200 → `DatasetError`); `extract_zip(body, destination)`; devuelve `version`.
4. CLI (`register_download_commands` se llama desde `register_dataset_commands` sobre el mismo `dataset_sub`):
   - `dataset download [--only NOMBRE ...]` → `set_defaults(handler=cmd_download, network=True)` (sin `key`).
   - `dataset prepare` → `set_defaults(handler=cmd_prepare, network=True)` (sin `key`).
   - `cmd_download`: `api_key = api_key_from_env(os.environ)`; `registry = load_registry(config.root_dir / REGISTRY_FILE)`;
     para cada entrada (filtrada por `--only` si se da; nombre desconocido → `DatasetError`): raíz `raw` =
     `resolve_within(config.root_dir, DETECTOR_ROOT / "datasets" / RAW_DIR)` si `detector`, o
     `resolve_within(config.root_dir, OCR_DATASETS_ROOT / RAW_DIR)` si `ocr`; `destination = resolve_within(raw, Path(name))`;
     si `destination / "data.yaml"` existe → escribe `f"{name}: ya descargado\n"`; si no, `download_dataset(..., sleep=time.sleep)`
     y escribe `f"{name}: descargado (versión {v})\n"`. Al final `write_sources_file(registry, raw_detector, config.root_dir / DETECTOR_ROOT / SOURCES_FILE)`
     y escribe `f"sources.yaml: {n} fuentes\n"`. Devuelve 0.
   - `cmd_prepare`: ejecuta `cmd_download` (con `args.only = None`) y luego, si no existen: `merge_detection(sources, raw_detector,
     resolve_within(config.root_dir, DETECTOR_ROOT / "datasets" / MERGED_OUTPUT))` y
     `chars_to_ocr(raw_ocr / "ocr_placas_colombia", resolve_within(config.root_dir, OCR_DATASETS_ROOT / OCR_OUTPUT), config.plate_catalog())`;
     si la salida ya existe escribe `"<salida>: ya preparado"`. Escribe los conteos de cada resumen. Devuelve 0.
   - Toda salida de consola: nombres de datasets y conteos; nunca la clave ni URLs.

## Casos borde y manejo de errores
- Sin `ROBOFLOW_API_KEY` → código de salida 2 (`ConfigurationError`), sin tocar la red.
- Una descarga fallida deja la carpeta destino sin `data.yaml` → se reintenta en la siguiente ejecución.

## Tests de aceptación
```python
# tests/unit/datasets/test_registry.py
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
    assert data["sources"][0]["url"] == "https://universe.roboflow.com/usco-thj9e/placas-colombia-ixdpr"
    with pytest.raises(DatasetError):
        write_sources_file(registry, tmp_path / "vacio", tmp_path / "s2.yaml")
```
```python
# tests/unit/infrastructure/test_dataset_fetcher.py
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from lector_placas.domain.errors import ConfigurationError, DatasetError, UnsafePathError
from lector_placas.infrastructure.dataset_fetcher import (
    api_key_from_env, download_dataset, export_link, extract_zip, latest_version,
)

KEY = "clave-sintetica-123"


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class FakeHttp:
    def __init__(self, responses: dict[str, list[tuple[int, bytes]]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[int, bytes]:
        self.calls.append(url)
        for prefix, queue in self.responses.items():
            if url.startswith(prefix):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"URL inesperada: {url}")


PROJECT = "https://api.roboflow.com/ws/proj?"
EXPORT = "https://api.roboflow.com/ws/proj/7/yolov8?"
LINK = "https://storage.example.org/export.zip"


def test_api_key_from_env() -> None:
    assert api_key_from_env({"ROBOFLOW_API_KEY": KEY}) == KEY
    with pytest.raises(ConfigurationError):
        api_key_from_env({})


def test_latest_version_picks_max_and_hides_key() -> None:
    body = json.dumps({"versions": [{"id": "ws/proj/3"}, {"id": "ws/proj/7"}]}).encode()
    assert latest_version(FakeHttp({PROJECT: [(200, body)]}), KEY, "ws", "proj") == 7
    with pytest.raises(DatasetError) as error:
        latest_version(FakeHttp({PROJECT: [(401, b"{}")]}), KEY, "ws", "proj")
    assert KEY not in str(error.value)
    with pytest.raises(DatasetError):
        latest_version(FakeHttp({PROJECT: [(200, b'{"versions": [{"id": "x/y/z"}]}')]}), KEY, "ws", "proj")
    with pytest.raises(DatasetError, match="sin versiones generadas: ws/proj"):
        latest_version(FakeHttp({PROJECT: [(200, b'{"versions": []}')]}), KEY, "ws", "proj")


def test_export_link_polls_until_ready() -> None:
    ready = json.dumps({"export": {"link": LINK}}).encode()
    http = FakeHttp({EXPORT: [(202, b'{"progress": 0.5}'), (202, b'{"progress": 0.9}'), (200, ready)]})
    sleeps: list[float] = []
    assert export_link(http, KEY, "ws", "proj", 7, "yolov8", sleeps.append) == LINK
    assert sleeps == [2.0, 2.0]
    assert all("nocache=true" in url for url in http.calls)


def test_export_link_rejects_non_https() -> None:
    bad = json.dumps({"export": {"link": "http://inseguro/x.zip"}}).encode()
    with pytest.raises(DatasetError):
        export_link(FakeHttp({EXPORT: [(200, bad)]}), KEY, "ws", "proj", 7, "yolov8", lambda s: None)


def test_extract_zip_blocks_zip_slip(tmp_path: Path) -> None:
    extract_zip(zip_bytes({"data.yaml": b"names: [placa]\n", "train/images/a.jpg": b"x"}), tmp_path / "ok")
    assert (tmp_path / "ok" / "data.yaml").exists()
    with pytest.raises(UnsafePathError):
        extract_zip(zip_bytes({"../fuera.txt": b"x"}), tmp_path / "malo")
    assert not (tmp_path / "fuera.txt").exists()
    with pytest.raises(DatasetError):
        extract_zip(b"no es zip", tmp_path / "roto")


def test_download_dataset_end_to_end(tmp_path: Path) -> None:
    project = json.dumps({"versions": [{"id": "ws/proj/7"}]}).encode()
    ready = json.dumps({"export": {"link": LINK}}).encode()
    http = FakeHttp({PROJECT: [(200, project)], EXPORT: [(200, ready)],
                     LINK: [(200, zip_bytes({"data.yaml": b"names: [placa]\n"}))]})
    assert download_dataset(http, KEY, "ws", "proj", "yolov8", tmp_path / "d", lambda s: None) == 7
    assert (tmp_path / "d" / "data.yaml").read_text() == "names: [placa]\n"
```
```python
# tests/unit/cli/test_dataset_download_cli.py
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


def test_missing_api_key_exits_2_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config").mkdir()
    for name in ("lector.yaml", "models.yaml", "datasets.yaml"):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    monkeypatch.setattr(cli_main.os, "umask", lambda mask: 0o022)
    code = cli_main.main(["--config", str(tmp_path / "config" / "lector.yaml"), "dataset", "download"])
    assert code == 2
    assert not (tmp_path / "training").exists()
```

## Fuera de alcance
Métrica del detector (spec 037) y métricas desde la revisión (spec 038). Entrenamiento (specs 030 y 032, ya existentes).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa) en verde; los tests no usan red.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -rnE "^\s*(import|from) (urllib|socket|requests|http)" src/ | grep -v "model_fetcher.py\|network_guard.py\|dataset_fetcher.py"` vacío.
- [ ] `grep -rn "api_key=\|ROBOFLOW_API_KEY" src/ | grep -iv "environ\|ENV_API_KEY\|api_key=api_key\|f\"{API_URL}"` sin prints ni logs de la clave.
