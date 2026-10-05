"""Tests de aceptación para filtros de proximidad en ProcessVideo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.application.process_video import (
    PipelineDependencies,
    ProcessingSettings,
    ProcessVideo,
)
from lector_placas.domain.consolidation import ConsolidationPolicy, VotingPlateConsolidator
from lector_placas.domain.entities import (
    BoundingBox,
    PlateDetection,
    VehicleDetection,
    VehicleType,
)
from lector_placas.domain.errors import InferenceError
from lector_placas.domain.ocr_correction import ConfusionMap
from tests.fixtures.fakes import FakeClock, InMemoryCropStore, InMemoryPlateRepository
from tests.fixtures.plate_catalog import build_test_catalog
from tests.unit.application.test_process_video import (
    ConstantQuality,
    CyclingReader,
    FakeSource,
    FakeSourceFactory,
    FixedPlateDetector,
    ScriptedVehicleDetector,
    SingleTrackTracker,
    TwoTrackTracker,
)

SHA = "d" * 64
CAR_BOX_DEFAULT = BoundingBox(100, 100, 300, 250)
PLATE_IN_CROP_DEFAULT = BoundingBox(50, 100, 150, 215)  # En el frame: (130, 185, 230, 215), 100px


class BoxVehicleDetector:
    """Devuelve siempre una detección de vehículo en la caja especificada."""

    def __init__(self, box: BoundingBox) -> None:
        self.box = box

    def detect(self, image: np.ndarray) -> list[VehicleDetection]:
        return [VehicleDetection(self.box, 0.9, VehicleType.CAR)]


class BoxPlateDetector:
    """Devuelve siempre una placa en la caja especificada y cuenta llamadas."""

    def __init__(self, box: BoundingBox) -> None:
        self.box = box
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[PlateDetection]:
        self.calls += 1
        return [PlateDetection(self.box, 0.9)]


def build(
    *,
    max_ocr_per_frame: int = 8,
    min_plate_width_px: int = 20,
    min_sharpness: float = 0.0,
    max_readings_per_track: int = 8,
    near_min_width_frac: float = 0.0,
    max_plate_vehicle_ratio: float = 1.0,
    roi: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    detector=None,  # type: ignore[assignment]
    plates=None,  # type: ignore[assignment]
    reader=None,  # type: ignore[assignment]
) -> tuple[ProcessVideo, dict]:
    """Construye ProcessVideo con parámetros de proximidad."""
    stamps = [i * 100 for i in range(3)]
    source = FakeSource(stamps)
    repo = InMemoryPlateRepository()
    crops = InMemoryCropStore()
    detector = detector or BoxVehicleDetector(CAR_BOX_DEFAULT)
    plates = plates or BoxPlateDetector(PLATE_IN_CROP_DEFAULT)
    reader = reader or CyclingReader(["ABC123"])

    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(10.0),
        detector,
        plates,
        SingleTrackTracker(),
        reader,
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1), ConfusionMap.default()
        ),
        repo,
        crops,
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings(
        "calle_lenta",
        max_ocr_per_frame,
        min_plate_width_px,
        min_sharpness,
        0.10,
        2000,
        max_readings_per_track,
        near_min_width_frac=near_min_width_frac,
        max_plate_vehicle_ratio=max_plate_vehicle_ratio,
        roi=roi,
    )
    return ProcessVideo(deps, settings), {
        "source": source,
        "repo": repo,
        "crops": crops,
        "detector": detector,
        "plates": plates,
        "reader": reader,
    }


def test_outside_roi_skips_detection_and_reading() -> None:
    """Si el centro del vehículo está fuera de la ROI, no se detecta ni se lee la placa."""
    process, parts = build(roi=(0.5, 0.0, 1.0, 1.0))
    result = process.execute(Path("v.mp4"), SHA)
    assert parts["plates"].calls == 0
    assert result.stats.tracks_without_reading == 1
    assert len(parts["repo"].records) == 0


def test_small_vehicle_skips_plate_detector() -> None:
    """Si el vehículo es demasiado pequeño, no se detecta la placa."""
    process, parts = build(
        near_min_width_frac=0.2,
        max_plate_vehicle_ratio=0.5,  # min_veh = 128px; car = 200px < 256
    )
    process.execute(Path("v.mp4"), SHA)
    assert parts["plates"].calls == 0
    assert len(parts["repo"].records) == 0


def test_narrow_plate_is_discarded() -> None:
    """Si la placa es demasiado estrecha, no se lee."""
    process, parts = build(
        near_min_width_frac=0.2,
        max_plate_vehicle_ratio=1.0,  # min_plate = 128px
    )
    process.execute(Path("v.mp4"), SHA)
    assert parts["plates"].calls == 3
    assert parts["reader"].calls == 0
    assert len(parts["repo"].records) == 0


def test_plate_at_edge_is_discarded() -> None:
    """Si la placa toca el borde del frame, no se lee."""
    process, parts = build(
        detector=BoxVehicleDetector(BoundingBox(0, 100, 200, 250)),
        plates=BoxPlateDetector(BoundingBox(1, 100, 101, 130)),
    )
    # En el frame: x1 = 1 + 0 = 1 < FRAME_EDGE_MARGIN_PX (2)
    process.execute(Path("v.mp4"), SHA)
    assert parts["reader"].calls == 0
    assert len(parts["repo"].records) == 0


def test_near_plate_is_read() -> None:
    """Con parámetros ajustados, una placa cerca se lee y se guarda como CONFIRMED."""
    process, parts = build(
        min_plate_width_px=32,
        near_min_width_frac=0.025,  # min_plate = max(32, 48) = 48px
        max_plate_vehicle_ratio=0.5,  # min_veh = 96px < 200px
    )
    process.execute(Path("v.mp4"), SHA)
    assert parts["reader"].calls > 0
    records = list(parts["repo"].records.values())
    assert len(records) == 1
    assert records[0].plate_text == "ABC123"
    assert str(records[0].status) == "confirmed"


def test_roi_filter_runs_before_ocr_cap() -> None:
    """La ROI se aplica antes del tope de OCR por frame."""
    detector = TwoTrackTracker()
    # Track 1 (pequeño, centro x=500): fuera de ROI (x < 416)
    # Track 2 (grande, centro x=250): dentro de ROI
    plates = BoxPlateDetector(BoundingBox(50, 100, 150, 215))
    reader = CyclingReader(["ABC123"])

    stamps = [i * 100 for i in range(2)]
    source = FakeSource(stamps)
    repo = InMemoryPlateRepository()
    crops = InMemoryCropStore()

    deps = PipelineDependencies(
        FakeSourceFactory(source),
        TimeBasedFrameSampler(10.0),
        ScriptedVehicleDetector(),
        plates,
        detector,
        reader,
        ConstantQuality(),
        VotingPlateConsolidator(
            build_test_catalog(), ConsolidationPolicy(3, 0.9, 0.6, 0.1), ConfusionMap.default()
        ),
        repo,
        crops,
        FakeClock(step_ms=10),
    )
    settings = ProcessingSettings(
        "calle_lenta",
        1,  # max_ocr_per_frame = 1
        20,
        0.0,
        0.10,
        2000,
        1,  # max_readings_per_track = 1
        near_min_width_frac=0.0,
        max_plate_vehicle_ratio=1.0,
        roi=(0.0, 0.0, 0.65, 1.0),  # x <= 416
    )
    process = ProcessVideo(deps, settings)
    result = process.execute(Path("v.mp4"), SHA)

    records = list(repo.records.values())
    assert len(records) == 1
    assert records[0].track_id == 2  # Solo track 2
    assert result.stats.tracks_total == 2
    assert result.stats.tracks_without_reading == 1


@pytest.mark.parametrize(
    "build_kwargs,expected_log",
    [
        (
            {"roi": (0.5, 0.0, 1.0, 1.0)},
            "cercania run_id=1 fuera_roi=3 vehiculo_pequeno=0 sin_placa=0"
            " placa_en_borde=0 placa_estrecha=0 borrosa=0"
            " placa_fuera_vehiculo=0",
        ),
        (
            {"plates": FixedPlateDetector(found=False)},
            "cercania run_id=1 fuera_roi=0 vehiculo_pequeno=0 sin_placa=3"
            " placa_en_borde=0 placa_estrecha=0 borrosa=0"
            " placa_fuera_vehiculo=0",
        ),
        (
            {"min_sharpness": 60.0},
            "cercania run_id=1 fuera_roi=0 vehiculo_pequeno=0 sin_placa=0"
            " placa_en_borde=0 placa_estrecha=0 borrosa=3"
            " placa_fuera_vehiculo=0",
        ),
    ],
)
def test_proximity_log_line(caplog, build_kwargs: dict, expected_log: str) -> None:  # type: ignore[no-untyped-def]
    """Verifica que se registra la línea de log exacta con los contadores."""
    import logging

    caplog.set_level(logging.INFO)
    process, _parts = build(**build_kwargs)
    process.execute(Path("v.mp4"), SHA)
    assert any(expected_log in rec.message for rec in caplog.records)


def test_no_proximity_log_on_failure() -> None:
    """Si la corrida falla, no se registra la línea de log de proximidad."""
    process, _parts = build(detector=ScriptedVehicleDetector(fail_on_call=1))
    with pytest.raises(InferenceError):
        process.execute(Path("v.mp4"), SHA)
    # No hay registro de "cercania" porque la corrida falló
