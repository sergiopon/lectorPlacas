from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "lector_placas"
STDLIB = frozenset(__import__("sys").stdlib_module_names) | {"__future__"}

FORBIDDEN_PREFIXES: dict[str, tuple[str, ...]] = {
    "application": (
        "lector_placas.adapters",
        "lector_placas.infrastructure",
        "lector_placas.cli",
        "lector_placas.evaluation",
        "lector_placas.datasets",
    ),
    "infrastructure": (
        "lector_placas.adapters",
        "lector_placas.cli",
        "lector_placas.evaluation",
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
