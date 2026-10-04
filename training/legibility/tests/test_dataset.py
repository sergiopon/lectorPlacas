from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from legibility_training.common import LegibilityError
from legibility_training.dataset import near_population, read_export


def test_read_export_parses_rows(tmp_path: Path) -> None:
    """Prueba que read_export parsea filas con celdas vacías."""
    # Crear directorio de exportación dentro de tmp_path
    export_dir = tmp_path / "test_export"
    export_dir.mkdir()

    # Escribir CSV con 2 filas
    csv_path = export_dir / "annotations.csv"
    columns = [
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
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "low_confidence",
                "plate_width_px": "60",
                "plate_height_px": "20",
                "sharpness": "99.0",
                "contrast": "64.0",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )
        writer.writerow(
            {
                "label": "borrosa",
                "human_reviewed": "1",
                "video_group": "2",
                "vehicle_type": "car",
                "confidence": "0.5",
                "agreement": "0.6",
                "num_readings": "2",
                "reasons": "",
                "plate_width_px": "",
                "plate_height_px": "",
                "sharpness": "",
                "contrast": "",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "unverified",
                "run_id": "1",
                "track_id": "2",
                "crop_ref": "xyz789",
                "created_at": "2024-01-01",
                "reviewed_at": "",
            }
        )

    # Parchear DATASETS_DIR
    with patch("legibility_training.dataset.DATASETS_DIR", tmp_path):
        rows = read_export(Path("test_export"))

    assert len(rows) == 2
    assert rows[0].label == "legible"
    assert rows[0].confidence == 0.8
    assert rows[0].plate_width_px == 60
    assert rows[0].reasons == ("low_confidence",)

    assert rows[1].label == "borrosa"
    assert rows[1].plate_width_px is None
    assert rows[1].reasons == ()


def test_read_export_rejects_bad_input(tmp_path: Path) -> None:
    """Prueba que read_export rechaza entrada inválida."""
    export_dir = tmp_path / "test_export"
    export_dir.mkdir()

    # Caso 1: columnas distintas
    csv_path = export_dir / "annotations.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bad", "columns"])

    with patch("legibility_training.dataset.DATASETS_DIR", tmp_path):
        with pytest.raises(LegibilityError, match="columnas inesperadas"):
            read_export(Path("test_export"))

    # Caso 2: confidence inválido
    csv_path.unlink()
    columns = [
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
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "x",  # inválido
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "",
                "plate_height_px": "",
                "sharpness": "",
                "contrast": "",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )

    with patch("legibility_training.dataset.DATASETS_DIR", tmp_path):
        with pytest.raises(LegibilityError, match="fila inválida: 1"):
            read_export(Path("test_export"))

    # Caso 3: ruta fuera de DATASETS_DIR
    with patch("legibility_training.dataset.DATASETS_DIR", tmp_path):
        with pytest.raises(LegibilityError, match="exportación no válida"):
            read_export(Path("../outside"))


def test_near_population(tmp_path: Path) -> None:
    """Prueba que near_population filtra correctamente."""
    export_dir = tmp_path / "test_export"
    export_dir.mkdir()

    csv_path = export_dir / "annotations.csv"
    columns = [
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
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        # Fila 1: ancho 47 en 1920x1080 (mínimo 48) → descartada
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "47",
                "plate_height_px": "20",
                "sharpness": "99.0",
                "contrast": "64.0",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )
        # Fila 2: ancho 48 en 1920x1080 (mínimo 48) → incluida
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "48",
                "plate_height_px": "20",
                "sharpness": "99.0",
                "contrast": "64.0",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )
        # Fila 3: human_reviewed falso → descartada
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "0",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "50",
                "plate_height_px": "20",
                "sharpness": "99.0",
                "contrast": "64.0",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )
        # Fila 4: sharpness vacía → descartada
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "50",
                "plate_height_px": "20",
                "sharpness": "",
                "contrast": "64.0",
                "frame_width": "1920",
                "frame_height": "1080",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )
        # Fila 5: ancho 32 en 1280x720 (mínimo 32) → incluida
        writer.writerow(
            {
                "label": "legible",
                "human_reviewed": "1",
                "video_group": "1",
                "vehicle_type": "car",
                "confidence": "0.8",
                "agreement": "0.75",
                "num_readings": "4",
                "reasons": "",
                "plate_width_px": "32",
                "plate_height_px": "16",
                "sharpness": "99.0",
                "contrast": "64.0",
                "frame_width": "1280",
                "frame_height": "720",
                "status": "confirmed",
                "run_id": "1",
                "track_id": "1",
                "crop_ref": "abc123",
                "created_at": "2024-01-01",
                "reviewed_at": "2024-01-02",
            }
        )

    with patch("legibility_training.dataset.DATASETS_DIR", tmp_path):
        rows = read_export(Path("test_export"))
        filtered = near_population(rows)

    # Solo filas 2 y 5 quedan
    assert len(filtered) == 2
    assert filtered[0].plate_width_px == 48
    assert filtered[1].plate_width_px == 32
