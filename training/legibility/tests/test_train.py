from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from legibility_training.dataset import Row
from legibility_training.evaluate import (
    baseline_rates,
    bootstrap_upper,
    choose_threshold,
    rates,
)
from legibility_training.train import main


def test_choose_threshold() -> None:
    """Prueba que choose_threshold elige correctamente."""
    # 20 legibles: los dos primeros tienen p_legible baja, el resto alta
    p_legible = np.array([0.505, 0.515] + [0.9] * 18)
    is_legible = np.ones(20, dtype=bool)

    # Con t=0.51: 1 oculto (5%)
    # Con t=0.52: 2 ocultos (10%)
    # MAX_HIDDEN_LEGIBLE = 0.05, así que devuelve 0.51

    t = choose_threshold(p_legible, is_legible)
    assert t == 0.51


def test_rates_and_baseline() -> None:
    """Prueba rates y baseline_rates."""
    p_legible = np.array([0.2, 0.8, 0.3, 0.9])
    is_legible = np.array([True, True, False, False])
    threshold = 0.5

    hidden_legible, hidden_unusable = rates(p_legible, is_legible, threshold)
    assert hidden_legible == 0.5  # 1 de 2 legibles
    assert hidden_unusable == 0.5  # 1 de 2 inservibles

    # Para baseline_rates, usamos filas con num_readings
    rows = [
        Row(
            label="legible",
            human_reviewed=True,
            video_group=1,
            vehicle_type="car",
            confidence=0.8,
            agreement=0.75,
            num_readings=1,  # Oculto por baseline
            reasons=(),
            plate_width_px=60,
            plate_height_px=20,
            sharpness=99.0,
            contrast=64.0,
            frame_width=1920,
            frame_height=1080,
        ),
        Row(
            label="legible",
            human_reviewed=True,
            video_group=1,
            vehicle_type="car",
            confidence=0.8,
            agreement=0.75,
            num_readings=3,  # No oculto
            reasons=(),
            plate_width_px=60,
            plate_height_px=20,
            sharpness=99.0,
            contrast=64.0,
            frame_width=1920,
            frame_height=1080,
        ),
        Row(
            label="borrosa",
            human_reviewed=True,
            video_group=1,
            vehicle_type="car",
            confidence=0.5,
            agreement=0.6,
            num_readings=1,  # Oculto
            reasons=(),
            plate_width_px=60,
            plate_height_px=20,
            sharpness=99.0,
            contrast=64.0,
            frame_width=1920,
            frame_height=1080,
        ),
        Row(
            label="no_placa",
            human_reviewed=True,
            video_group=1,
            vehicle_type="car",
            confidence=0.3,
            agreement=0.4,
            num_readings=5,  # No oculto
            reasons=(),
            plate_width_px=60,
            plate_height_px=20,
            sharpness=99.0,
            contrast=64.0,
            frame_width=1920,
            frame_height=1080,
        ),
    ]

    bl, bi = baseline_rates(rows)
    assert bl == 0.5  # 1 de 2 legibles ocultos
    assert bi == 0.5  # 1 de 2 inservibles ocultos


def test_bootstrap_upper_deterministic() -> None:
    """Prueba que bootstrap_upper es determinístico."""
    p_legible = np.array([0.1, 0.2, 0.3, 0.4, 0.5] * 20)
    is_legible = np.ones(100, dtype=bool)
    groups = np.array([i % 5 for i in range(100)])

    upper1 = bootstrap_upper(p_legible, is_legible, groups, 0.25, seed=42)
    upper2 = bootstrap_upper(p_legible, is_legible, groups, 0.25, seed=42)

    assert upper1 == upper2
    assert 0 <= upper1 <= 1


def test_train_end_to_end(tmp_path: Path) -> None:
    """Prueba end-to-end de train.py."""
    # Crear datasets_dir en tmp_path
    datasets_dir = tmp_path / "datasets"
    export_dir = datasets_dir / "test_export"
    export_dir.mkdir(parents=True)

    # Crear runs_dir
    runs_dir = tmp_path / "runs"

    # Generar CSV sintético con 5 grupos y 120 filas por clase
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

    rng = np.random.default_rng(0)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        for class_idx, label in enumerate(["legible", "borrosa", "no_placa"]):
            for i in range(120):
                video_group = (i % 5) + 1  # Grupos 1-5

                # Características separables como en test_fit_separates_classes
                if class_idx == 0:  # legible
                    confidence = 0.9 + rng.normal(0, 0.05)
                elif class_idx == 1:  # borrosa
                    confidence = 0.3 + rng.normal(0, 0.05)
                else:  # no_placa
                    confidence = 0.1 + rng.normal(0, 0.05)

                confidence = max(0.0, min(1.0, confidence))

                writer.writerow(
                    {
                        "label": label,
                        "human_reviewed": "1",
                        "video_group": str(video_group),
                        "vehicle_type": "car",
                        "confidence": str(confidence),
                        "agreement": "0.75",
                        "num_readings": "4",
                        "reasons": "",
                        "plate_width_px": "60",
                        "plate_height_px": "20",
                        "sharpness": "99.0",
                        "contrast": "64.0",
                        "frame_width": "1920",
                        "frame_height": "1080",
                        "status": "confirmed",
                        "run_id": "1",
                        "track_id": str(i),
                        "crop_ref": f"crop{i}",
                        "created_at": "2024-01-01",
                        "reviewed_at": "2024-01-02",
                    }
                )

    # Parchear directorios
    with patch("legibility_training.dataset.DATASETS_DIR", datasets_dir):
        with patch("legibility_training.train.DATASETS_DIR", datasets_dir):
            with patch("legibility_training.train.RUNS_DIR", runs_dir):
                result = main(["--export", "test_export", "--name", "prueba"])

    assert result == 0

    # Verificar que se crearon los archivos
    run_dirs = list(runs_dir.glob("prueba/*/"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    model_path = run_dir / "model.json"
    report_path = run_dir / "report.json"

    assert model_path.exists()
    assert report_path.exists()

    # Verificar permisos
    assert oct(model_path.stat().st_mode)[-3:] == "600"
    assert oct(report_path.stat().st_mode)[-3:] == "600"

    # Verificar contenido de model.json
    with open(model_path) as f:
        model_data = json.load(f)

    assert model_data["version"] == 1
    assert len(model_data["features"]) == 16
    assert model_data["classes"] == ["legible", "borrosa", "no_placa"]
    assert len(model_data["weights"]) == 3
    assert len(model_data["weights"][0]) == 16
    assert len(model_data["bias"]) == 3
    assert 0 <= model_data["threshold"] <= 0.99

    # Verificar contenido de report.json
    with open(report_path) as f:
        report_data = json.load(f)

    assert report_data["n"]["legible"] == 120
    assert report_data["n"]["borrosa"] == 120
    assert report_data["n"]["no_placa"] == 120
    assert report_data["video_groups"] == 5
    assert "conditions" in report_data
    assert "verdict" in report_data


def test_train_insufficient_data(tmp_path: Path) -> None:
    """Prueba que train rechaza datos insuficientes."""
    # Crear datasets_dir en tmp_path
    datasets_dir = tmp_path / "datasets"
    export_dir = datasets_dir / "test_export"
    export_dir.mkdir(parents=True)

    # Crear runs_dir
    runs_dir = tmp_path / "runs"

    # CSV con insuficientes datos (99 de no_placa)
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

        for i in range(99):
            writer.writerow(
                {
                    "label": "no_placa",
                    "human_reviewed": "1",
                    "video_group": str((i % 5) + 1),
                    "vehicle_type": "car",
                    "confidence": "0.3",
                    "agreement": "0.4",
                    "num_readings": "2",
                    "reasons": "",
                    "plate_width_px": "60",
                    "plate_height_px": "20",
                    "sharpness": "99.0",
                    "contrast": "64.0",
                    "frame_width": "1920",
                    "frame_height": "1080",
                    "status": "unverified",
                    "run_id": "1",
                    "track_id": str(i),
                    "crop_ref": f"crop{i}",
                    "created_at": "2024-01-01",
                    "reviewed_at": "",
                }
            )

    # Parchear directorios
    with patch("legibility_training.dataset.DATASETS_DIR", datasets_dir):
        with patch("legibility_training.train.DATASETS_DIR", datasets_dir):
            with patch("legibility_training.train.RUNS_DIR", runs_dir):
                result = main(["--export", "test_export", "--name", "prueba"])

    assert result == 1
