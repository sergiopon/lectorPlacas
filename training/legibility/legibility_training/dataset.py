from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from legibility_training.common import (
    DATASETS_DIR,
    MIN_PLATE_WIDTH_PX,
    NEAR_MIN_WIDTH_FRAC,
    LegibilityError,
)


@dataclass(frozen=True, slots=True)
class Row:
    """Una fila del dataset de legibilidad."""

    label: str
    human_reviewed: bool
    video_group: int
    vehicle_type: str
    confidence: float
    agreement: float
    num_readings: int
    reasons: tuple[str, ...]
    plate_width_px: int | None
    plate_height_px: int | None
    sharpness: float | None
    contrast: float | None
    frame_width: int | None
    frame_height: int | None


def read_export(export_dir: Path) -> list[Row]:
    """Lee la exportación de `lector dataset export-legibility`."""
    # Resolver dentro de DATASETS_DIR
    resolved_dir = (DATASETS_DIR / export_dir).resolve()

    # Verificar que está dentro de DATASETS_DIR
    try:
        resolved_dir.relative_to(DATASETS_DIR.resolve())
    except ValueError as e:
        raise LegibilityError("exportación no válida") from e

    export_dir = resolved_dir

    # Verificar que es un directorio
    if not export_dir.is_dir():
        raise LegibilityError("exportación no válida")

    csv_path = export_dir / "annotations.csv"
    if not csv_path.exists():
        raise LegibilityError("exportación no válida")

    rows = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise LegibilityError("columnas inesperadas")

            # Verificar que tiene exactamente las 20 columnas esperadas
            expected_columns = {
                "label",
                "human_reviewed",
                "video_group",
                "vehicle_type",
                "confidence",
                "agreement",
                "num_readings",
                "reasons",
                "plate_width_px",
                "plate_height_px",
                "sharpness",
                "contrast",
                "frame_width",
                "frame_height",
                "status",
                "run_id",
                "track_id",
                "crop_ref",
                "created_at",
                "reviewed_at",
            }
            if set(reader.fieldnames) != expected_columns:
                raise LegibilityError("columnas inesperadas")

            for row_num, row_dict in enumerate(reader, start=1):
                try:
                    label = row_dict["label"]
                    human_reviewed = row_dict["human_reviewed"] == "1"
                    video_group = int(row_dict["video_group"])
                    vehicle_type = row_dict["vehicle_type"]
                    confidence = float(row_dict["confidence"])
                    agreement = float(row_dict["agreement"])
                    num_readings = int(row_dict["num_readings"])

                    reasons_str = row_dict["reasons"].strip()
                    reasons = tuple(reasons_str.split("|")) if reasons_str else ()

                    plate_width_px = (
                        int(row_dict["plate_width_px"])
                        if row_dict["plate_width_px"].strip()
                        else None
                    )
                    plate_height_px = (
                        int(row_dict["plate_height_px"])
                        if row_dict["plate_height_px"].strip()
                        else None
                    )
                    sharpness = (
                        float(row_dict["sharpness"]) if row_dict["sharpness"].strip() else None
                    )
                    contrast = float(row_dict["contrast"]) if row_dict["contrast"].strip() else None
                    frame_width = (
                        int(row_dict["frame_width"]) if row_dict["frame_width"].strip() else None
                    )
                    frame_height = (
                        int(row_dict["frame_height"]) if row_dict["frame_height"].strip() else None
                    )

                    rows.append(
                        Row(
                            label=label,
                            human_reviewed=human_reviewed,
                            video_group=video_group,
                            vehicle_type=vehicle_type,
                            confidence=confidence,
                            agreement=agreement,
                            num_readings=num_readings,
                            reasons=reasons,
                            plate_width_px=plate_width_px,
                            plate_height_px=plate_height_px,
                            sharpness=sharpness,
                            contrast=contrast,
                            frame_width=frame_width,
                            frame_height=frame_height,
                        )
                    )
                except (ValueError, KeyError) as e:
                    raise LegibilityError(f"fila inválida: {row_num}") from e
    except LegibilityError:
        raise
    except Exception as e:
        raise LegibilityError("exportación no válida") from e

    return rows


def near_population(rows: Sequence[Row]) -> list[Row]:
    """Filtra filas de población cercana.

    Conserva las filas revisadas, con todas las medidas, y ancho >= mínimo.
    """
    result = []
    for row in rows:
        # Debe ser human_reviewed
        if not row.human_reviewed:
            continue

        # Todos los campos de medida deben estar presentes
        if (
            row.plate_width_px is None
            or row.plate_height_px is None
            or row.sharpness is None
            or row.contrast is None
            or row.frame_width is None
            or row.frame_height is None
        ):
            continue

        # Ancho >= mínimo
        frame_max = max(row.frame_width, row.frame_height)
        min_width = math.ceil(
            round(
                max(MIN_PLATE_WIDTH_PX, NEAR_MIN_WIDTH_FRAC * frame_max),
                6,
            )
        )
        if row.plate_width_px < min_width:
            continue

        result.append(row)

    return result
