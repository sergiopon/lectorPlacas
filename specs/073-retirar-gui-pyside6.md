# 073 - Retirar la GUI de escritorio PySide6

> **Condición para lanzarla:** las specs 066–071 integradas y la web cubre, comprobado por el orquestador en el modo
> demo, todas las funciones de la GUI: procesar con progreso y cancelación, galería con filtros y búsqueda, revisión
> (confirmar, corregir, descartar, borrosa, saltar), exportar CSV, purgar y métricas. Si falta alguna, no se lanza.

## Objetivo
Eliminar la capa `gui` (PySide6), su script `lector-gui`, su dependencia y sus tests, para que el proyecto tenga una sola
interfaz gráfica: la web (ADR-016). La ventana OpenCV de revisión de la CLI (`lector review`, spec 034) se mantiene.

## Depende de
071 (y todas las anteriores).

## Archivos rectores aplicables
- ADR-016 (sustituye a ADR-015), reglas-seguridad.md SEG-27 (queda retirada), ARQUITECTURA.md §2 y §7. Los actualiza el
  orquestador al integrar, junto con README, CLAUDE.md y CONTEXT.md.

## Archivos a crear/modificar
- Borrar el directorio completo `src/lector_placas/gui/`.
- Borrar el directorio completo `tests/unit/gui/`.
- `pyproject.toml`: quitar `"PySide6-Essentials==6.11.2"` de `dependencies` y la línea `lector-gui = "lector_placas.gui.app:main"`
  de `[project.scripts]`. Nada más.
- `uv.lock` (regenerado con `uv lock`).
- `tests/architecture/test_dependency_rule.py`.

## Dependencias externas
Se elimina `PySide6-Essentials==6.11.2` (y lo que `uv lock` retire con ella). No se añade nada.

## Comportamiento esperado
1. Tras borrar, ningún archivo de `src/` ni de `tests/` contiene la cadena `lector_placas.gui` ni importa `PySide6`.
   Si alguno (fuera de los directorios borrados) la contiene, **detente y reporta** la lista: no lo edites.
2. `tests/architecture/test_dependency_rule.py`:
   - Quitar `"lector_placas.gui"` de todas las tuplas de `FORBIDDEN_PREFIXES` y quitar la clave `"gui"`.
   - Borrar el test `test_gui_imports_from_cli_only_composition`.
   - Sustituir `test_nobody_outside_gui_imports_pyside6` por `test_nobody_imports_pyside6`: ningún archivo de `src/`
     importa `PySide6` (raíz del nombre importado).
   - Añadir `test_gui_package_is_gone`: `(SRC / "gui").exists()` es `False`.
   - En la clave `"web"`, la tupla queda `("lector_placas.datasets",)`.
3. `uv lock` y `uv sync --locked`.

## Casos borde y manejo de errores
- Si `uv lock` retira también `shiboken6` u otros paquetes de Qt, es lo esperado. Si cambia la versión de cualquier otro
  paquete, **detente y reporta** el diff de `uv.lock`.

## Tests de aceptación (en prosa)
- Los tests de arquitectura modificados (comportamiento 2) pasan.
- `pyproject.toml` ya no contiene `lector-gui` ni `PySide6` (lo comprueba el último punto del Definition of Done).
- El resto de la suite pasa sin cambios.

## Fuera de alcance
- README, CLAUDE.md, CONTEXT.md, ARQUITECTURA.md, reglas-seguridad.md, ADR-015/016 y docs/00 (RF-36): los actualiza
  el orquestador al integrar.

## Definition of Done
- [ ] `uv lock` y `uv sync --locked` sin errores.
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -rn "PySide6\|lector_placas.gui" src tests pyproject.toml` sin resultados.
