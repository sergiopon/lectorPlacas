# 074 - Clave maestra desde un archivo (para Docker secrets)

## Objetivo
Permitir que la clave maestra se lea de un **archivo privado** cuando no hay keyring (dentro de un contenedor). Si la
variable de entorno `LECTOR_KEY_FILE` tiene una ruta absoluta, el proveedor de clave es el de archivo; si no, el del
keyring (comportamiento actual). Dos comandos nuevos escriben ese archivo: `lector key export-file` (copia la clave del
keyring, para usar los mismos datos en Docker) y `lector key init-file` (genera una clave nueva, sin keyring).

## Depende de
008, 028.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-02 (actualizada por el orquestador para esta spec), SEG-04, SEG-05, SEG-20, SEG-26.
- ADR-005 (actualización 2026-10-03), docs/08-plan-legibilidad-y-web.md §4.8.

## Archivos a crear/modificar
- `src/lector_placas/adapters/security/file_key_provider.py` (nuevo)
- `src/lector_placas/cli/composition.py` (`build_key_provider`)
- `src/lector_placas/cli/commands.py` (`cmd_key_init`, `cmd_key_export_file`, `cmd_key_init_file`)
- `src/lector_placas/cli/main.py` (subcomandos `key export-file` y `key init-file`)
- `tests/unit/adapters/test_file_key_provider.py` (nuevo)
- `tests/unit/cli/test_key_file_commands.py` (nuevo)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados

### `adapters/security/file_key_provider.py`
- `KEY_FILE_ENV: Final[str] = "LECTOR_KEY_FILE"`.
- `class FileKeyProvider` con `__init__(self, path: Path)` y `master_key(self) -> bytes` (implementa `KeyProvider`).
- `def write_key_file(path: Path, key: bytes) -> None`.
- Reutiliza `HEX_KEY_REGEX` y `KEY_SIZE` de `adapters/security/keyring_key_provider.py` (importados).

### `cli/composition.py`
`build_key_provider(create_if_missing: bool) -> KeyProvider`: si `os.environ.get(KEY_FILE_ENV)` es una cadena no vacía,
devuelve `FileKeyProvider(Path(valor))` (el argumento `create_if_missing` se ignora); si no, `KeyringKeyProvider(create_if_missing)`.

### `cli/main.py` y `cli/commands.py`
- `key export-file RUTA`: `set_defaults(handler=commands.cmd_key_export_file, network=False, key="load")`, argumento
  posicional `path` (`Path`).
- `key init-file RUTA`: `set_defaults(handler=commands.cmd_key_init_file, network=False)` **sin** `key` (no toca el
  keyring), argumento posicional `path` (`Path`).

## Comportamiento esperado

### 1. `FileKeyProvider.master_key()`
Con caché en memoria (la segunda llamada no vuelve a leer el archivo). En este orden; cada fallo lanza
`KeyUnavailableError` con el mensaje exacto indicado (nunca con contenido del archivo):
1. Si `path` no es absoluta → `"LECTOR_KEY_FILE debe ser una ruta absoluta"`.
2. `st = os.lstat(path)`; `FileNotFoundError` → `"archivo de clave no encontrado"`; otro `OSError` →
   `"archivo de clave no legible"`.
3. Si no es un archivo regular (`stat.S_ISREG(st.st_mode)` falso, incluidos enlaces simbólicos) →
   `"el archivo de clave debe ser un archivo regular"`.
4. Si `st.st_uid != os.getuid()` → `"el archivo de clave pertenece a otro usuario"`.
5. Si `st.st_mode & 0o077 != 0` → `"el archivo de clave tiene permisos demasiado abiertos"`.
6. Lee el contenido como texto ASCII; `OSError` o `UnicodeDecodeError` → `"archivo de clave no legible"`. Quita un único
   `"\n"` final si lo hay. Si no cumple `HEX_KEY_REGEX` → `"el archivo de clave está corrupto"`.
7. Devuelve `bytes.fromhex(texto)` (32 bytes) y lo guarda en caché.

### 2. `write_key_file(path, key)`
1. Si `len(key) != KEY_SIZE` → `KeyUnavailableError("clave maestra inválida")`.
2. `fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)`; `FileExistsError` →
   `KeyUnavailableError("el archivo de clave ya existe")`; otro `OSError` → `KeyUnavailableError("no se pudo escribir el archivo de clave")`.
3. Escribe `key.hex() + "\n"` en ASCII y cierra. Después `os.chmod(path, 0o400)`.

### 3. Comandos
- `cmd_key_init` (existente): si `KEY_FILE_ENV` está definida con valor no vacío, escribe
  `"clave maestra disponible en el archivo de clave\n"`; si no, el texto actual (`"clave maestra disponible en el keyring\n"`).
  En ambos casos llama antes a `require_keys(args).master_key()` (sin cambios).
- `cmd_key_export_file(args, config)`: `write_key_file(args.path, require_keys(args).master_key())`; escribe
  `"clave maestra copiada al archivo indicado (0400)\n"`; devuelve 0.
- `cmd_key_init_file(args, config)`: `write_key_file(args.path, os.urandom(KEY_SIZE))`; escribe
  `"clave maestra nueva escrita en el archivo indicado (0400)\n"`; devuelve 0.
- Ningún comando escribe la clave ni la ruta en el log.

## Casos borde y manejo de errores
- Archivo con modo 0600 del propio usuario: válido. 0640, 0644 o 0444: rechazado (paso 5).
- `LECTOR_KEY_FILE` definida pero vacía: se usa el keyring.
- `key export-file` sin clave en el keyring: falla en el prefetch con el error actual de `KeyringKeyProvider`.

## Tests de aceptación (en prosa)
Fixtures sintéticos: claves generadas en el test (`bytes(range(32))`).

`tests/unit/adapters/test_file_key_provider.py` (en `tmp_path`):
- `test_reads_valid_key_file`: un archivo con `bytes(range(32)).hex() + "\n"` y modo 0400 devuelve `bytes(range(32))`;
  lo mismo sin el salto final y con modo 0600; tras borrar el archivo, una segunda llamada devuelve la clave en caché.
- `test_rejects_relative_path`: `FileKeyProvider(Path("clave.txt")).master_key()` lanza `KeyUnavailableError` con el
  mensaje `LECTOR_KEY_FILE debe ser una ruta absoluta`.
- `test_rejects_missing_and_symlink`: un archivo inexistente → `archivo de clave no encontrado`; un enlace simbólico a un
  archivo válido → `el archivo de clave debe ser un archivo regular`; un directorio → el mismo mensaje.
- `test_rejects_open_permissions` (parametrizado con 0o640, 0o644 y 0o444) → `el archivo de clave tiene permisos
  demasiado abiertos`.
- `test_rejects_other_owner`: con `monkeypatch` de `os.getuid` para devolver `os.getuid() + 1` →
  `el archivo de clave pertenece a otro usuario`.
- `test_rejects_corrupt`: contenidos `"xyz"`, 63 caracteres hex, 64 en mayúsculas y 64 con `"\n\n"` final →
  `el archivo de clave está corrupto`; el mensaje nunca contiene el contenido.
- `test_write_key_file`: escribe `bytes(range(32))` en `tmp_path/k`; el modo es 0400, el contenido es el hex más `"\n"`
  y `FileKeyProvider` lo lee; escribir otra vez en la misma ruta lanza `el archivo de clave ya existe`; una clave de
  31 bytes lanza `clave maestra inválida`.

`tests/unit/cli/test_key_file_commands.py`:
- `test_build_key_provider_selects_file`: con `monkeypatch.setenv("LECTOR_KEY_FILE", "/x/k")`,
  `composition.build_key_provider(False)` es un `FileKeyProvider`; con la variable vacía o sin definir, es un
  `KeyringKeyProvider`.
- `test_parser_registers_key_file_commands`: `key export-file /tmp/k` se analiza con `key == "load"`,
  `network is False` y `path == Path("/tmp/k")`; `key init-file /tmp/k` no tiene atributo `key` (o es `None`) y
  `network is False`.
- `test_cmd_key_init_file_and_export`: `cmd_key_init_file` con `path` en `tmp_path` crea un archivo 0400 legible por
  `FileKeyProvider` y escribe el mensaje exacto; `cmd_key_export_file` con `args.keys` = `FakeKeyProvider()` escribe en
  otro archivo la clave de `FakeKeyProvider` y su mensaje exacto.
- `test_cmd_key_init_message_with_file`: con `LECTOR_KEY_FILE` definida y `args.keys` = `FakeKeyProvider()`,
  `cmd_key_init` escribe `clave maestra disponible en el archivo de clave`.

## Fuera de alcance
- Imagen y `compose.yaml` (spec 075).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa, incluidos `tests/review`) en verde.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] `grep -rn "master_key()\|\.hex()" src/lector_placas | grep -i "log\|print"` sin resultados.
