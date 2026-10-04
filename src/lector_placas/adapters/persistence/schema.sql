CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    video_sha256           TEXT    NOT NULL CHECK (length(video_sha256) = 64
                                                   AND video_sha256 NOT GLOB '*[^0-9a-f]*'),
    profile                TEXT    NOT NULL CHECK (length(profile) BETWEEN 1 AND 64),
    width                  INTEGER NOT NULL CHECK (width > 0),
    height                 INTEGER NOT NULL CHECK (height > 0),
    rotation_deg           INTEGER NOT NULL CHECK (rotation_deg IN (0, 90, 180, 270)),
    duration_ms            INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    started_at             TEXT    NOT NULL,
    finished_at            TEXT,
    status                 TEXT    NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    frames_decoded         INTEGER CHECK (frames_decoded IS NULL OR frames_decoded >= 0),
    frames_processed       INTEGER CHECK (frames_processed IS NULL OR frames_processed >= 0),
    tracks_total           INTEGER CHECK (tracks_total IS NULL OR tracks_total >= 0),
    sightings_confirmed    INTEGER CHECK (sightings_confirmed IS NULL OR sightings_confirmed >= 0),
    sightings_unverified   INTEGER CHECK (sightings_unverified IS NULL OR sightings_unverified >= 0),
    tracks_without_reading INTEGER CHECK (tracks_without_reading IS NULL OR tracks_without_reading >= 0),
    processing_ms          INTEGER CHECK (processing_ms IS NULL OR processing_ms >= 0)
);

CREATE TABLE IF NOT EXISTS plates (
    plate_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_text    TEXT NOT NULL UNIQUE CHECK (length(plate_text) BETWEEN 1 AND 10
                                              AND plate_text NOT GLOB '*[^A-Z0-9]*'),
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sightings (
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
    status        TEXT    NOT NULL CHECK (status IN ('confirmed', 'unverified', 'rejected', 'corrected', 'illegible')),
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
    duplicate_of    INTEGER REFERENCES sightings(sighting_id) ON DELETE SET NULL CHECK (duplicate_of IS NULL OR duplicate_of <> sighting_id),
    UNIQUE (run_id, track_id, first_seen_ms),
    CHECK ((plate_width_px IS NULL) = (plate_height_px IS NULL) AND (plate_width_px IS NULL) = (sharpness IS NULL) AND (plate_width_px IS NULL) = (contrast IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_sightings_status     ON sightings(status);
CREATE INDEX IF NOT EXISTS idx_sightings_created_at ON sightings(created_at);
CREATE INDEX IF NOT EXISTS idx_sightings_plate_id   ON sightings(plate_id);
CREATE INDEX IF NOT EXISTS idx_sightings_crop_ref   ON sightings(crop_ref) WHERE crop_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_started_at      ON runs(started_at);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL CHECK (event IN ('run_started', 'run_finished', 'review', 'purge', 'export')),
    occurred_at TEXT NOT NULL,
    detail      TEXT NOT NULL CHECK (length(detail) <= 500)
);
