"""Tests de aceptación para `build_processing_settings` (spec 057)."""

from __future__ import annotations

from pathlib import Path

from lector_placas.cli.composition import build_processing_settings
from lector_placas.infrastructure.config import load_config

ROOT = Path(__file__).resolve().parents[3]
REAL = ROOT / "config" / "lector.yaml"


def test_build_processing_settings_copies_profile() -> None:
    """Verifica que build_processing_settings copia correctamente todos los campos del perfil."""
    config = load_config(REAL)
    name, profile = config.profile("patrulla")

    settings = build_processing_settings(name, profile)

    assert settings.profile_name == "patrulla"
    assert settings.max_ocr_per_frame == 8
    assert settings.min_plate_width_px == 32
    assert settings.min_sharpness == 0.0
    assert settings.vehicle_crop_margin == 0.10
    assert settings.track_finalize_after_ms == 1000
    assert settings.max_readings_per_track == 6
    assert settings.near_min_width_frac == 0.025
    assert settings.max_plate_vehicle_ratio == 0.5
    assert settings.roi == (0.0, 0.0, 1.0, 1.0)
    assert settings.early_stop is True
    assert settings.dedup_window_ms == 30000
