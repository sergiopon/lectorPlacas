# 042 - GUI de escritorio: dependencia, arranque, sesión y ventana principal

## Objetivo
Crear el paquete `lector_placas.gui` (segundo composition root, ADR-015) con el comando `lector-gui`: arranque seguro
(umask, configuración, logging, clave, guardia de red), sesión con la BD abierta y purga inicial, y una ventana principal
con tres pestañas vacías que llenan las specs 043, 044 y 045.

## Depende de
028, 041.

## Archivos rectores aplicables
- ADR-015 (decisión, resultado de la prueba de convivencia).
- ARQUITECTURA.md §2 (capa `gui`, reglas 3 y 6), §6 (`except Exception` permitido en `gui/app.py`), §7 (GUI).
- reglas-seguridad.md SEG-03 (purga al abrir la sesión), SEG-04 (umask), SEG-20 (guardia antes de la `QApplication`),
  SEG-23 (versión fijada), SEG-24 (pip-audit), SEG-26, SEG-27.

## Archivos a crear/modificar
- `pyproject.toml` (dependencia y script)
- `uv.lock`
- `src/lector_placas/cli/composition.py` (recibe `validated_video`)
- `src/lector_placas/cli/commands.py` (importa `validated_video` desde `composition`)
- `src/lector_placas/gui/__init__.py` (nuevo, docstring de una línea)
- `src/lector_placas/gui/app.py` (nuevo)
- `src/lector_placas/gui/session.py` (nuevo)
- `src/lector_placas/gui/main_window.py` (nuevo)
- `src/lector_placas/gui/images.py` (nuevo)
- `tests/architecture/test_dependency_rule.py` (capa `gui`)
- `tests/architecture/test_gui_rules.py` (nuevo)
- `tests/unit/gui/__init__.py`, `tests/unit/gui/conftest.py` (nuevos)
- `tests/unit/gui/test_app.py`, `tests/unit/gui/test_session.py`, `tests/unit/gui/test_main_window.py`,
  `tests/unit/gui/test_images.py` (nuevos)

## Dependencias externas
- `PySide6-Essentials==6.11.2` en `[project].dependencies` (verificado en PyPI el 2026-09-27: licencia
  LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, Python >=3.10,<3.15; trae `QtCore`, `QtGui`, `QtWidgets` y `QtTest`;
  depende solo de `shiboken6==6.11.2`). **No** se usa el metapaquete `PySide6` (añade `PySide6-Addons`, ~400 MB más).
- `[project.scripts]`: `lector-gui = "lector_placas.gui.app:main"`.
- Regenerar `uv.lock` con `uv lock` y verificar con `uv sync --locked`. Si la resolución falla, detente y reporta.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# cli/composition.py — se mueve aquí desde cli/commands.py, mismo cuerpo y docstring
def validated_video(config: AppConfig, path: Path) -> Path: ...

# gui/images.py
def bgr_to_qimage(image: ImageBGR) -> QImage: ...

# gui/session.py
@dataclass(slots=True)
class GuiSession:
    config: AppConfig
    keys: KeyProvider
    clock: Clock
    repository: PlateRepository
    browser: SightingBrowser
    crop_store: CropStore
    export_store: ExportStore
    def close(self) -> None: ...

def open_session(config: AppConfig, keys: KeyProvider) -> tuple[GuiSession, PurgeResult]: ...

# gui/main_window.py
WINDOW_TITLE: Final[str] = "lectorPlacas"
TAB_TITLES: Final[tuple[str, str, str]] = ("Procesar", "Avistamientos", "Exportar y retención")
class MainWindow(QMainWindow):
    def __init__(self, session: GuiSession, purge: PurgeResult) -> None: ...
    def tabs(self) -> QTabWidget: ...
    def closeEvent(self, event: QCloseEvent) -> None: ...

# gui/app.py
DEFAULT_CONFIG_PATH: Final[Path] = Path("config/lector.yaml")
LOG_FILENAME: Final[str] = "lector.log"
KEY_HINT: Final[str] = "Cree la clave con: lector key init"
UNEXPECTED_MESSAGE: Final[str] = "error inesperado; revise logs/lector.log"
def main(argv: Sequence[str] | None = None) -> int: ...
def prepare(argv: Sequence[str] | None) -> tuple[AppConfig, KeyProvider]: ...
def _create_application() -> QApplication: ...      # punto de sustitución para tests
def _exec(app: QApplication) -> int: ...             # punto de sustitución para tests: devuelve app.exec()
```

## Comportamiento esperado
1. **`validated_video`** pasa de `cli/commands.py` a `cli/composition.py` sin cambios de lógica. `commands.py` la importa
   con `from lector_placas.cli.composition import validated_video`, de modo que `commands.validated_video` sigue
   existiendo (la usa `evaluation_commands.py`). Los tests existentes de la CLI pasan sin cambios.
2. **`prepare(argv)`**: `argparse` con un único argumento opcional `--config` (`Path`, por defecto `DEFAULT_CONFIG_PATH`);
   `load_config`; `configure_logging(config.logging.level, config.under_root(config.paths.log_dir) / LOG_FILENAME)`;
   `keys = composition.build_key_provider(False)` y `keys.master_key()` (la clave se lee **antes** de la guardia, SEG-20).
   Devuelve `(config, keys)`. No crea la clave: si no existe, `KeyUnavailableError`.
3. **`main(argv)`**, en este orden:
   1. `os.umask(0o077)` como primera instrucción.
   2. `prepare(argv)` dentro de `try`; si lanza `LectorPlacasError` se guarda el error.
   3. `network_guard.block_network()` **siempre** (haya fallado `prepare` o no), antes de crear la `QApplication`.
   4. `app = _create_application()`: devuelve `QApplication.instance()` si existe o crea una con `["lector-gui"]`;
      `setApplicationName("lectorPlacas")`.
   5. Si `prepare` falló: `QMessageBox.critical(None, WINDOW_TITLE, texto)` donde `texto` es `str(error)` y, si el error
      es `KeyUnavailableError`, además una línea nueva con `KEY_HINT`; registra `arranque fallido error=<TipoDeError>` y
      devuelve 1.
   6. Instala `sys.excepthook` con una función que registra con `logger.critical(..., exc_info=...)` y muestra
      `QMessageBox.critical(None, WINDOW_TITLE, UNEXPECTED_MESSAGE)`; la ventana sigue abierta.
   7. `session, purge = open_session(config, keys)`; si lanza `LectorPlacasError` → diálogo con `str(error)`, registro y
      devuelve 1.
   8. `window = MainWindow(session, purge)`, `window.show()`, `code = _exec(app)`; en `finally` `session.close()`.
      Devuelve `code`.
   Un `except Exception` de último nivel en `main` (permitido por ARQUITECTURA §6) registra con `logger.exception` y
   devuelve 1. Ningún mensaje contiene texto de placa (SEG-26).
4. **`open_session(config, keys)`**: `clock = SystemClock()`; `repository = composition.build_repository(config, keys)`;
   dentro de `try`: `crop_store = composition.build_crop_store(config, keys)`,
   `export_store = composition.build_export_store(config)`,
   `purge = composition.build_purge(config, repository, crop_store, export_store, clock).execute()` (SEG-03) y
   `browser = repository.browser()`. Si algo lanza, cierra el repositorio y relanza. Devuelve la sesión y el resultado
   de la purga. `GuiSession.close()` cierra el repositorio y es idempotente.
5. **`MainWindow`**:
   - Título fijo `WINDOW_TITLE` (nunca incluye texto de placa, SEG-27); tamaño inicial 1200×800.
   - Widget central: `QTabWidget` con tres pestañas con los títulos de `TAB_TITLES`; en esta spec cada una es un
     `QWidget` vacío con un `QLabel` "Disponible en una versión posterior".
   - Barra de estado con `f"Purga al abrir: recortes={…} avistamientos={…} corridas={…} placas={…} exportaciones={…}"`
     tomando los campos de `PurgeResult` (mismos nombres que usa `cmd_purge`).
   - `tabs()` devuelve el `QTabWidget` (las specs siguientes reemplazan las pestañas con `removeTab`/`insertTab`).
   - `closeEvent`: `session.close()` y acepta el evento.
6. **`bgr_to_qimage(image)`**: exige `ndim == 3`, 3 canales y `dtype uint8` (si no, `InvalidEntityError`); convierte
   BGR→RGB con `cv2.cvtColor`, crea un `QImage` `Format_RGB888` con `bytesPerLine = 3 * ancho` y devuelve una **copia**
   (`QImage.copy()`) para que no dependa de la memoria del arreglo. No escribe a disco.
7. **Regla de dependencia** (`tests/architecture/test_dependency_rule.py`):
   - Añadir `"lector_placas.gui"` a la tupla de prefijos prohibidos de **todas** las capas existentes y añadir una
     entrada `"cli": ("lector_placas.gui",)`.
   - Nuevo test: los módulos de `gui/` que importan algo de `lector_placas.cli` solo importan exactamente
     `lector_placas.cli.composition` (o `from lector_placas.cli import composition`).
   - Nuevo test: ningún módulo fuera de `gui/` importa `PySide6`.
8. **`tests/architecture/test_gui_rules.py`** (SEG-27, ADR-015): recorre el texto de `src/lector_placas/gui/*.py` y
   falla si aparece alguno de: `QSettings`, `QtNetwork`, `QClipboard`, `clipboard(`, `imshow`, `namedWindow`, o una
   llamada `setWindowTitle(` cuyo argumento no sea un único nombre de constante en mayúsculas (expresión regular
   `setWindowTitle\((?![A-Z][A-Z0-9_]*\))`): los títulos son constantes y nunca llevan texto de placa.

## Casos borde y manejo de errores
- Ejecutar sin sesión gráfica: Qt aborta al crear la `QApplication`; no se intenta manejar (no es un
  `LectorPlacasError`). NO VERIFICADO el mensaje exacto.
- `--config` fuera de `config/` del repo: `load_config` ya falla con su error; se muestra en el diálogo.
- El log `lector.log` es el mismo archivo de la CLI.

## Tests de aceptación
Todos los tests de `tests/unit/gui/` corren sin pantalla: `tests/unit/gui/conftest.py` fija
`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` **antes** de importar PySide6 y ofrece un fixture de sesión
`qapp` que devuelve `QApplication.instance()` o crea una. Ningún test abre diálogos reales: `QMessageBox.critical` se
sustituye con `monkeypatch` por una función que registra sus argumentos. Fixtures sintéticos (SEG-10).

1. `test_images.py`:
   - `test_bgr_to_qimage_converts_channels`: imagen 4×3 con un píxel BGR `(255, 0, 0)` → `QImage.pixelColor` es azul
     puro; tamaño `(3, 4)` en ancho×alto; formato `Format_RGB888`.
   - `test_bgr_to_qimage_is_independent_copy`: modificar el arreglo tras convertir no cambia el `QImage`.
   - `test_bgr_to_qimage_rejects_invalid_arrays`: gris 2D, 4 canales y `float32` lanzan `InvalidEntityError`.
2. `test_session.py` (sustituye con `monkeypatch` las funciones de `composition` por fakes de `tests/fixtures/fakes.py`;
   `InMemoryPlateRepository` ya implementa `SightingBrowser` y `browser()` desde la spec 041):
   - `test_open_session_purges_and_returns_result`: la purga se ejecuta una vez y su resultado se devuelve.
   - `test_open_session_closes_repository_on_failure`: si `build_crop_store` lanza `CropStoreError`, el repositorio
     queda cerrado y el error se propaga.
   - `test_session_close_is_idempotent`.
3. `test_main_window.py`:
   - `test_window_title_and_tabs`: título `lectorPlacas`; tres pestañas con los títulos de `TAB_TITLES`.
   - `test_status_bar_shows_purge_counts`.
   - `test_close_event_closes_session`.
4. `test_app.py` (sustituye `network_guard.block_network`, `os.umask`, `composition.build_key_provider`,
   `app._create_application`, `app._exec`, `app.open_session` y `QMessageBox.critical`; usa una config real del repo o
   la del fixture `project` de `tests/integration/test_cli_end_to_end.py` como referencia):
   - `test_main_order_umask_key_guard_application`: registra el orden de llamadas y comprueba
     `umask` → `master_key` → `block_network` → `_create_application`.
   - `test_main_blocks_network_even_if_prepare_fails`: con `KeyUnavailableError` en `master_key`, `block_network` se
     llama, se muestra el diálogo con `KEY_HINT` en el texto y `main` devuelve 1.
   - `test_main_returns_exec_code_and_closes_session`: `_exec` devuelve 0 → `main` devuelve 0 y la sesión se cerró.
   - `test_main_session_error_shows_dialog`: `open_session` lanza `RepositoryError("x")` → diálogo con `"x"` y 1.
5. Arquitectura: los dos tests nuevos de `test_dependency_rule.py` y `test_gui_rules.py` pasan; los existentes también.

## Definition of Done
- `uv sync --locked` instala `PySide6-Essentials 6.11.2` y `uv run lector-gui --help` muestra la ayuda de argparse.
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run pytest -m integration tests/integration/test_cli_end_to_end.py` pasa (la CLI no cambió de comportamiento).
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores. Si los stubs de PySide6 obligan a
  un `# type: ignore[<código>]`, se permite solo en `gui/` y con el código explícito.
- `uv run pip-audit` sin vulnerabilidades nuevas; si aparece alguna en PySide6/shiboken6, detente y reporta.
