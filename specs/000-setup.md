# 000 - Setup del proyecto

## Objetivo
Crear el entorno reproducible (uv, Python 3.13), la estructura de paquetes, la configuración de
calidad (ruff, mypy, pytest, pre-commit), `.gitignore`, licencia y verificación de GPU.

## Depende de
Ninguna.

## Archivos rectores aplicables
- ARQUITECTURA.md §2 (regla de dependencia, verificada por test), §5 (estructura), §6 (convenciones: límites de ruff).
- ADR-008 (LICENSE AGPL-3.0), ADR-009 (onnxruntime-gpu), ADR-011 (Python 3.13, uv, override de OpenCV).
- reglas-seguridad.md: SEG-11 (.gitignore), SEG-23 (versiones fijadas + lock), SEG-24 (pip-audit), SEG-25 (sin secretos).

## Archivos a crear/modificar
- `.python-version`
- `pyproject.toml`
- `.gitignore`
- `.pre-commit-config.yaml`
- `LICENSE` (descargado, ver paso 5)
- `src/lector_placas/__init__.py`
- `src/lector_placas/{domain,application,infrastructure,adapters,evaluation,datasets,cli}/__init__.py`
- `src/lector_placas/adapters/{video,inference,tracking,imaging,persistence,storage,security,review,export}/__init__.py`
- `tests/__init__.py`, `tests/architecture/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/__init__.py`
- `tests/architecture/test_dependency_rule.py`
- `tests/integration/test_gpu_environment.py`
- `scripts/verify_gpu.py`
- `uv.lock` (generado por `uv lock`)

## Dependencias externas
Exactamente las listadas en `pyproject.toml` de abajo. Herramienta: uv 0.12.19 (instalación:
`curl -LsSf https://astral.sh/uv/0.12.19/install.sh | sh` — si esta URL falla, detente y reporta).

## Interfaces y tipos involucrados
Ninguno (setup).

## Comportamiento esperado
1. `.python-version` contiene exactamente `3.13` y un salto de línea.
2. `pyproject.toml` con este contenido **literal**:
```toml
[project]
name = "lector-placas"
version = "0.1.0"
description = "ALPR local para placas colombianas"
requires-python = "==3.13.*"
license = "AGPL-3.0-only"
dependencies = [
    "numpy==2.5.3",
    "opencv-python==4.14.0.94",
    "av==18.1.0",
    "onnxruntime-gpu[cuda,cudnn]==1.30.0",
    "fast-plate-ocr==1.1.0",
    "open-image-models==0.6.0",
    "trackers==2.6.0",
    "supervision==0.30.5",
    "scipy==1.18.1",
    "sqlcipher3==0.6.2",
    "cryptography==50.0.1",
    "keyring==25.7.0",
    "pydantic==2.13.5",
    "PyYAML==6.0.3",
]

[project.scripts]
lector = "lector_placas.cli.main:main"

[dependency-groups]
dev = [
    "pytest==9.1.1",
    "ruff==0.16.9",
    "mypy==2.3.1",
    "pre-commit==4.6.2",
    "pip-audit==2.10.1",
    "onnx==1.23.0",
    "types-PyYAML==6.0.12.20260906",
]

[build-system]
requires = ["uv_build==0.12.19"]
build-backend = "uv_build"

[tool.uv]
override-dependencies = ["opencv-python-headless; sys_platform == 'never'"]

[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "tests"]
extend-exclude = ["training", "*.md"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "C90", "S", "ANN", "D", "RUF", "SIM", "PTH", "BLE", "PL"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.mccabe]
max-complexity = 8

[tool.ruff.lint.pylint]
max-args = 6
max-statements = 20
max-branches = 8
max-returns = 4

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "ANN", "D", "PLR2004", "PLR0913", "PLC0415", "S311", "N817", "E501", "S603", "S108"]
"scripts/**" = ["T201", "S603", "S607"]

[tool.mypy]
python_version = "3.13"
strict = true
mypy_path = "src"
packages = ["lector_placas"]

[[tool.mypy.overrides]]
module = [
    "onnxruntime.*", "sqlcipher3.*", "trackers.*", "supervision.*", "open_image_models.*",
    "fast_plate_ocr.*", "keyring.*", "scipy.*", "onnx.*",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "gpu: requiere GPU NVIDIA y drivers",
    "integration: usa librerías nativas reales (PyAV, SQLCipher, ONNX Runtime, keyring)",
]
```
3. `.gitignore` con este contenido literal:
```
# Entorno
.venv/
__pycache__/
*.py[cod]
.mypy_cache/
.ruff_cache/
.pytest_cache/
.env
.env.*
# Datos personales y artefactos (SEG-11)
data/
models/
logs/
videos/
*.db
*.db-*
/*.csv
training/**/datasets/
training/**/runs/
training/**/weights/
training/**/.venv/
```
4. `.pre-commit-config.yaml` literal (hooks locales, sin repos remotos):
```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check .
        language: system
        pass_filenames: false
      - id: ruff-format
        name: ruff format --check
        entry: uv run ruff format --check .
        language: system
        pass_filenames: false
      - id: mypy
        name: mypy
        entry: uv run mypy src
        language: system
        pass_filenames: false
      - id: pytest
        name: pytest (sin gpu)
        entry: uv run pytest -m "not gpu" -q
        language: system
        pass_filenames: false
      - id: pip-audit
        name: pip-audit
        entry: uv run pip-audit
        language: system
        pass_filenames: false
```
5. `LICENSE`: `curl -fsSL https://www.gnu.org/licenses/agpl-3.0.txt -o LICENSE`. No escribas el texto a mano.
6. `src/lector_placas/__init__.py`: docstring `"""lectorPlacas: ALPR local para placas colombianas."""`,
   `from __future__ import annotations` y `__version__: str = "0.1.0"`. Los demás `__init__.py`:
   solo `"""<nombre del paquete>."""` y `from __future__ import annotations`.
7. `scripts/verify_gpu.py`: función `main() -> int` que:
   (a) ejecuta `subprocess.run(["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"], capture_output=True, text=True, check=False)`;
   (b) importa `onnxruntime`, llama `onnxruntime.preload_dlls(directory="")` y obtiene `onnxruntime.get_available_providers()`;
   (c) imprime `gpu=<name> compute_cap=<cap>` y `providers=<lista>`;
   (d) devuelve 0 si `compute_cap == "12.0"` y `"CUDAExecutionProvider"` está en la lista; si no, imprime la causa y devuelve 1.
   `if __name__ == "__main__": raise SystemExit(main())`.
8. `tests/architecture/test_dependency_rule.py`: recorre con `ast` todos los `.py` de `src/lector_placas/<capa>/`
   y verifica los imports según la tabla del test (código abajo).
9. `tests/integration/test_gpu_environment.py`: marcado `gpu`; ejecuta `scripts/verify_gpu.py` y exige código 0.
10. Ejecuta `uv lock` y `uv sync --locked`. Verifica que `opencv-python-headless` **no** esté instalado:
    `uv pip show opencv-python-headless` debe fallar (código ≠ 0).

## Casos borde y manejo de errores
- Si `uv lock` no resuelve: detente y reporta la salida completa. No cambies versiones.
- Si `uv pip show opencv-python-headless` lo encuentra instalado: detente y reporta (el override no funcionó).
- `verify_gpu.py` no debe lanzar excepción si `nvidia-smi` no existe: captura `FileNotFoundError`, imprime `nvidia-smi no encontrado` y devuelve 1.

## Tests de aceptación
```python
# tests/architecture/test_dependency_rule.py
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "lector_placas"
STDLIB = frozenset(__import__("sys").stdlib_module_names) | {"__future__"}

FORBIDDEN_PREFIXES: dict[str, tuple[str, ...]] = {
    "application": (
        "lector_placas.adapters", "lector_placas.infrastructure", "lector_placas.cli",
        "lector_placas.evaluation", "lector_placas.datasets",
    ),
    "infrastructure": (
        "lector_placas.adapters", "lector_placas.cli", "lector_placas.evaluation",
        "lector_placas.datasets",
    ),
    "adapters": ("lector_placas.cli", "lector_placas.evaluation", "lector_placas.datasets"),
    "evaluation": ("lector_placas.cli", "lector_placas.datasets"),
    "datasets": ("lector_placas.cli", "lector_placas.evaluation"),
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _files(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def test_domain_imports_only_stdlib_and_itself() -> None:
    for path in _files("domain"):
        for name in _imports(path):
            root = name.split(".")[0]
            assert root in STDLIB or name.startswith("lector_placas.domain"), f"{path}: {name}"


def test_application_imports_only_domain_numpy_and_stdlib() -> None:
    for path in _files("application"):
        for name in _imports(path):
            root = name.split(".")[0]
            allowed = (
                root in STDLIB
                or root == "numpy"
                or name.startswith(("lector_placas.domain", "lector_placas.application"))
            )
            assert allowed, f"{path}: {name}"


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_PREFIXES))
def test_layer_does_not_import_forbidden_layers(layer: str) -> None:
    for path in _files(layer):
        for name in _imports(path):
            assert not name.startswith(FORBIDDEN_PREFIXES[layer]), f"{path}: {name}"


def test_nobody_imports_torch_or_ultralytics() -> None:
    for path in sorted(SRC.rglob("*.py")):
        for name in _imports(path):
            assert name.split(".")[0] not in {"torch", "ultralytics", "pickle"}, f"{path}: {name}"
```
```python
# tests/integration/test_gpu_environment.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.gpu
def test_verify_gpu_script_reports_blackwell_and_cuda_provider() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_gpu.py")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "compute_cap=12.0" in result.stdout
```

## Fuera de alcance
Código de producción de cualquier capa; `config/*.yaml` (specs 006 y 019); entornos de `training/` (specs 030 y 032).

## Definition of Done
- [ ] `uv lock` y `uv sync --locked` terminan sin error; `uv.lock` creado.
- [ ] `uv pip show opencv-python-headless` devuelve código ≠ 0.
- [ ] `uv run pytest -m "not gpu"` pasa (tests de arquitectura en verde).
- [ ] `uv run pytest -m gpu` pasa en la PC con RTX 5050.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` sin errores.
- [ ] `uv run pip-audit` ejecutado; salida reportada.
- [ ] `LICENSE` descargado de gnu.org (no escrito a mano).
