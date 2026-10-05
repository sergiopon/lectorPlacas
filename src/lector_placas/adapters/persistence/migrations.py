"""Migración del esquema de la base de datos SQLCipher de las versiones 1 a 2 y 2 a 3.

La versión 1 no admite `'illegible'` en el `CHECK` de `sightings.status`. SQLite no permite
modificar un `CHECK` con `ALTER TABLE`, así que la tabla se recrea dentro de una transacción
explícita, conservando `sighting_id` y el resto de columnas sin cambios.

La versión 2 a 3 agrega columnas de calidad (`plate_width_px`, `plate_height_px`, `sharpness`,
`contrast`) y `duplicate_of` a la tabla `sightings` con restricciones de integridad.
La versión 3 a 4 añade `frame_ms` y `box_x/box_y/box_w/box_h`.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

import sqlcipher3.dbapi2 as sqlcipher

from lector_placas.domain.errors import RepositoryError

logger = logging.getLogger(__name__)

_MIGRATION_FAILED: Final[str] = "migración de esquema fallida"

_CREATE_SIGHTINGS_V2: Final[str] = """
CREATE TABLE sightings_v2 (
    sighting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    plate_id      INTEGER REFERENCES plates(plate_id) ON DELETE SET NULL,
    track_id      INTEGER NOT NULL CHECK (track_id >= 0),
    first_seen_ms INTEGER NOT NULL CHECK (first_seen_ms >= 0),
    last_seen_ms  INTEGER NOT NULL CHECK (last_seen_ms >= first_seen_ms),
    vehicle_type  TEXT    NOT NULL CHECK (vehicle_type IN ('car', 'motorcycle', 'bus', 'truck')),
    ocr_text      TEXT    NOT NULL CHECK (length(ocr_text) BETWEEN 1 AND 10
                                          AND ocr_text NOT GLOB '*[^A-Z0-9]*'),
    plate_text    TEXT    NOT NULL CHECK (length(plate_text) BETWEEN 1 AND 10
                                          AND plate_text NOT GLOB '*[^A-Z0-9]*'),
    confidence    REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    agreement     REAL    NOT NULL CHECK (agreement BETWEEN 0.0 AND 1.0),
    num_readings  INTEGER NOT NULL CHECK (num_readings >= 1),
    status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified', 'rejected',
                                                     'corrected', 'illegible')),
    reasons       TEXT    NOT NULL,
    format_ids    TEXT    NOT NULL,
    crop_ref      TEXT CHECK (crop_ref IS NULL OR (length(crop_ref) = 32
                                                   AND crop_ref NOT GLOB '*[^0-9a-f]*')),
    created_at    TEXT    NOT NULL,
    reviewed_at   TEXT,
    UNIQUE (run_id, track_id, first_seen_ms)
)
"""

# Lista de columnas fija (no se interpola: evita SEG-15 y el falso positivo de S608).
_INSERT_SIGHTINGS_V2: Final[str] = """
INSERT INTO sightings_v2 (
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
)
SELECT
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
FROM sightings
"""

_RECREATE_INDEXES: Final[tuple[str, ...]] = (
    "CREATE INDEX IF NOT EXISTS idx_sightings_status     ON sightings(status)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_created_at ON sightings(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_plate_id   ON sightings(plate_id)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_crop_ref   ON sightings(crop_ref) "
    "WHERE crop_ref IS NOT NULL",
)

_CREATE_SIGHTINGS_V3: Final[str] = """
CREATE TABLE sightings_v3 (
    sighting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    plate_id      INTEGER REFERENCES plates(plate_id) ON DELETE SET NULL,
    track_id      INTEGER NOT NULL CHECK (track_id >= 0),
    first_seen_ms INTEGER NOT NULL CHECK (first_seen_ms >= 0),
    last_seen_ms  INTEGER NOT NULL CHECK (last_seen_ms >= first_seen_ms),
    vehicle_type  TEXT    NOT NULL CHECK (vehicle_type IN ('car', 'motorcycle', 'bus', 'truck')),
    ocr_text      TEXT    NOT NULL CHECK (length(ocr_text) BETWEEN 1 AND 10
                                          AND ocr_text NOT GLOB '*[^A-Z0-9]*'),
    plate_text    TEXT    NOT NULL CHECK (length(plate_text) BETWEEN 1 AND 10
                                          AND plate_text NOT GLOB '*[^A-Z0-9]*'),
    confidence    REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    agreement     REAL    NOT NULL CHECK (agreement BETWEEN 0.0 AND 1.0),
    num_readings  INTEGER NOT NULL CHECK (num_readings >= 1),
    status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified', 'rejected',
                                                     'corrected', 'illegible')),
    reasons       TEXT    NOT NULL,
    format_ids    TEXT    NOT NULL,
    crop_ref      TEXT CHECK (crop_ref IS NULL OR (length(crop_ref) = 32
                                                   AND crop_ref NOT GLOB '*[^0-9a-f]*')),
    created_at    TEXT    NOT NULL,
    reviewed_at   TEXT,
    plate_width_px  INTEGER CHECK (plate_width_px IS NULL OR plate_width_px >= 1),
    plate_height_px INTEGER CHECK (plate_height_px IS NULL OR plate_height_px >= 1),
    sharpness       REAL    CHECK (sharpness IS NULL OR sharpness >= 0.0),
    contrast        REAL    CHECK (contrast IS NULL OR contrast >= 0.0),
    duplicate_of    INTEGER REFERENCES sightings(sighting_id)
                             ON DELETE SET NULL
                             CHECK (duplicate_of IS NULL OR duplicate_of <> sighting_id),
    UNIQUE (run_id, track_id, first_seen_ms),
    CHECK ((plate_width_px IS NULL) = (plate_height_px IS NULL)
           AND (plate_width_px IS NULL) = (sharpness IS NULL)
           AND (plate_width_px IS NULL) = (contrast IS NULL))
)
"""

# Lista de columnas fija (18 columnas de v2, las 4 nuevas quedan NULL).
_INSERT_SIGHTINGS_V3: Final[str] = """
INSERT INTO sightings_v3 (
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
)
SELECT
    sighting_id, run_id, plate_id, track_id, first_seen_ms, last_seen_ms, vehicle_type,
    ocr_text, plate_text, confidence, agreement, num_readings, status, reasons,
    format_ids, crop_ref, created_at, reviewed_at
FROM sightings
"""

_RECREATE_INDEXES_V3: Final[tuple[str, ...]] = (
    "CREATE INDEX IF NOT EXISTS idx_sightings_status     ON sightings(status)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_created_at ON sightings(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_plate_id   ON sightings(plate_id)",
    "CREATE INDEX IF NOT EXISTS idx_sightings_crop_ref   ON sightings(crop_ref) "
    "WHERE crop_ref IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_sightings_duplicate_of ON sightings(duplicate_of) "
    "WHERE duplicate_of IS NOT NULL",
)

_ADD_COLUMNS_V4: Final[tuple[str, ...]] = (
    "ALTER TABLE sightings ADD COLUMN frame_ms INTEGER CHECK (frame_ms IS NULL OR frame_ms >= 0)",
    "ALTER TABLE sightings ADD COLUMN box_x INTEGER CHECK (box_x IS NULL OR box_x >= 0)",
    "ALTER TABLE sightings ADD COLUMN box_y INTEGER CHECK (box_y IS NULL OR box_y >= 0)",
    "ALTER TABLE sightings ADD COLUMN box_w INTEGER CHECK (box_w IS NULL OR box_w >= 1)",
    "ALTER TABLE sightings ADD COLUMN box_h INTEGER CHECK (box_h IS NULL OR box_h >= 1)",
)


def migrate_v1_to_v2(connection: sqlcipher.Connection) -> None:
    """Migra el esquema de avistamientos de la versión 1 a la 2.

    Recrea `sightings` con el `CHECK` de `status` ampliado para admitir `'illegible'`, conservando
    filas, `sighting_id`, índices y el contador de `AUTOINCREMENT`.

    Args:
        connection: conexión SQLCipher abierta sobre una base de datos en esquema v1.

    Raises:
        RepositoryError: si la migración falla. La base de datos queda en v1 intacta (el DDL de
            SQLite es transaccional).
    """
    connection.execute("PRAGMA foreign_keys = OFF")
    original_isolation_level = connection.isolation_level
    connection.isolation_level = None
    try:
        count = _migrate_sightings_table(connection)
    finally:
        connection.isolation_level = original_isolation_level
    _check_foreign_keys(connection)
    logger.info("esquema migrado de v1 a v2 avistamientos=%d", count)


def _migrate_sightings_table(connection: sqlcipher.Connection) -> int:
    """Recrea `sightings` dentro de una transacción explícita y devuelve las filas copiadas.

    Si `BEGIN IMMEDIATE` falla (p. ej. la base de datos está bloqueada por otra conexión), no
    hay transacción que deshacer. Si falla un paso posterior, se intenta el `ROLLBACK`, pero un
    fallo de ese `ROLLBACK` no oculta el error original.
    """
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlcipher.Error as e:
        raise RepositoryError(_MIGRATION_FAILED) from e
    try:
        connection.execute(_CREATE_SIGHTINGS_V2)
        cursor = connection.execute(_INSERT_SIGHTINGS_V2)
        count = cursor.rowcount
        connection.execute("DROP TABLE sightings")
        connection.execute("ALTER TABLE sightings_v2 RENAME TO sightings")
        for statement in _RECREATE_INDEXES:
            connection.execute(statement)
        connection.execute("UPDATE schema_version SET version = 2")
        connection.execute("COMMIT")
    except sqlcipher.Error as e:
        with contextlib.suppress(sqlcipher.Error):
            connection.execute("ROLLBACK")
        raise RepositoryError(_MIGRATION_FAILED) from e
    return int(count)


def migrate_v2_to_v3(connection: sqlcipher.Connection) -> None:
    """Migra el esquema de avistamientos de la versión 2 a la 3.

    Recrea `sightings` con las columnas nuevas de calidad (`plate_width_px`, `plate_height_px`,
    `sharpness`, `contrast`) y `duplicate_of`, conservando filas, `sighting_id`, índices y el
    contador de `AUTOINCREMENT`. Las columnas nuevas se inicializan con `NULL`.

    Args:
        connection: conexión SQLCipher abierta sobre una base de datos en esquema v2.

    Raises:
        RepositoryError: si la migración falla. La base de datos queda en v2 intacta (el DDL de
            SQLite es transaccional).
    """
    connection.execute("PRAGMA foreign_keys = OFF")
    original_isolation_level = connection.isolation_level
    connection.isolation_level = None
    try:
        count = _migrate_sightings_table_v3(connection)
    finally:
        connection.isolation_level = original_isolation_level
    _check_foreign_keys(connection)
    logger.info("esquema migrado de v2 a v3 avistamientos=%d", count)


def _migrate_sightings_table_v3(connection: sqlcipher.Connection) -> int:
    """Recrea `sightings` a v3 dentro de una transacción explícita y devuelve las filas copiadas.

    Si `BEGIN IMMEDIATE` falla (p. ej. la base de datos está bloqueada por otra conexión), no
    hay transacción que deshacer. Si falla un paso posterior, se intenta el `ROLLBACK`, pero un
    fallo de ese `ROLLBACK` no oculta el error original.
    """
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlcipher.Error as e:
        raise RepositoryError(_MIGRATION_FAILED) from e
    try:
        connection.execute(_CREATE_SIGHTINGS_V3)
        cursor = connection.execute(_INSERT_SIGHTINGS_V3)
        count = cursor.rowcount
        connection.execute("DROP TABLE sightings")
        connection.execute("ALTER TABLE sightings_v3 RENAME TO sightings")
        for statement in _RECREATE_INDEXES_V3:
            connection.execute(statement)
        connection.execute("UPDATE schema_version SET version = 3")
        connection.execute("COMMIT")
    except sqlcipher.Error as e:
        with contextlib.suppress(sqlcipher.Error):
            connection.execute("ROLLBACK")
        raise RepositoryError(_MIGRATION_FAILED) from e
    return int(count)


def migrate_v3_to_v4(connection: sqlcipher.Connection) -> None:
    """Migra el esquema de avistamientos de la versión 3 a la 4.

    Añade `frame_ms` y `box_x`, `box_y`, `box_w`, `box_h` a `sightings`; las filas existentes
    quedan con `NULL` en las cinco columnas.

    Args:
        connection: conexión SQLCipher abierta sobre una base de datos en esquema v3.

    Raises:
        RepositoryError: si la migración falla. La base de datos queda en v3 intacta (el DDL de
            SQLite es transaccional).
    """
    original_isolation_level = connection.isolation_level
    connection.isolation_level = None
    try:
        _migrate_sightings_table_v4(connection)
    finally:
        connection.isolation_level = original_isolation_level
    logger.info("esquema migrado de v3 a v4")


def _migrate_sightings_table_v4(connection: sqlcipher.Connection) -> None:
    """Añade las columnas de ubicación a `sightings` dentro de una transacción explícita."""
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlcipher.Error as e:
        raise RepositoryError(_MIGRATION_FAILED) from e
    try:
        for statement in _ADD_COLUMNS_V4:
            connection.execute(statement)
        connection.execute("UPDATE schema_version SET version = 4")
        connection.execute("COMMIT")
    except sqlcipher.Error as e:
        with contextlib.suppress(sqlcipher.Error):
            connection.execute("ROLLBACK")
        raise RepositoryError(_MIGRATION_FAILED) from e


def _check_foreign_keys(connection: sqlcipher.Connection) -> None:
    """Comprueba la integridad referencial tras la migración y reactiva `foreign_keys`."""
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    connection.execute("PRAGMA foreign_keys = ON")
    if violations:
        raise RepositoryError(_MIGRATION_FAILED)
