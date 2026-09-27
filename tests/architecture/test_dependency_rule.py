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
        "lector_placas.gui",
    ),
    "infrastructure": (
        "lector_placas.adapters",
        "lector_placas.cli",
        "lector_placas.evaluation",
        "lector_placas.datasets",
        "lector_placas.gui",
    ),
    "adapters": (
        "lector_placas.cli",
        "lector_placas.evaluation",
        "lector_placas.datasets",
        "lector_placas.gui",
    ),
    "evaluation": ("lector_placas.cli", "lector_placas.datasets", "lector_placas.gui"),
    "datasets": ("lector_placas.cli", "lector_placas.evaluation", "lector_placas.gui"),
    "cli": ("lector_placas.gui",),
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


def test_gui_imports_from_cli_only_composition() -> None:
    for path in _files("gui"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("lector_placas.cli"), f"{path}: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if not node.module.startswith("lector_placas.cli"):
                    continue
                allowed = node.module == "lector_placas.cli.composition" or (
                    node.module == "lector_placas.cli"
                    and all(alias.name == "composition" for alias in node.names)
                )
                assert allowed, f"{path}: {node.module}"


def test_nobody_outside_gui_imports_pyside6() -> None:
    for path in sorted(SRC.rglob("*.py")):
        if "gui" in path.relative_to(SRC).parts:
            continue
        for name in _imports(path):
            assert name.split(".")[0] != "PySide6", f"{path}: {name}"
