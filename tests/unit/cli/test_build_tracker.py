from __future__ import annotations

from pathlib import Path

from lector_placas.adapters.tracking.botsort_tracker import TrackerSettings
from lector_placas.cli import composition
from lector_placas.infrastructure.config import load_config

REAL = Path(__file__).resolve().parents[3] / "config" / "lector.yaml"


def test_build_tracker_uses_profile_cmc() -> None:
    config = load_config(REAL)
    captured_settings = []

    class Fake:
        def __init__(self, settings: TrackerSettings) -> None:
            captured_settings.append(settings)

    import lector_placas.cli.composition

    original = lector_placas.cli.composition.BotSortTracker
    try:
        lector_placas.cli.composition.BotSortTracker = Fake  # type: ignore
        for test_value in [True, False]:
            captured_settings.clear()
            profile = config.profiles["calle_lenta"].model_copy(
                update={"camera_motion_compensation": test_value}
            )
            composition.build_tracker(config, profile)
            assert len(captured_settings) == 1
            settings = captured_settings[0]
            assert isinstance(settings, TrackerSettings)
            assert settings.enable_cmc is test_value
            assert settings.frame_rate == 15.0
    finally:
        lector_placas.cli.composition.BotSortTracker = original
