"""Tests de aceptación para las funciones de filtro de proximidad."""

from __future__ import annotations

import pytest

from lector_placas.application.proximity import (
    ProximityCounters,
    center_in_box,
    center_in_roi,
    effective_min_width,
    touches_frame_edge,
    validate_roi,
)
from lector_placas.domain.entities import BoundingBox


class TestEffectiveMinWidth:
    """Tests parametrizados de `effective_min_width`."""

    @pytest.mark.parametrize(
        "frame_width,frame_height,min_width_px,frac,expected",
        [
            (1280, 720, 32, 0.025, 32),
            (1920, 1080, 32, 0.025, 48),
            (1080, 1920, 32, 0.025, 48),
            (3840, 2160, 32, 0.025, 96),
            (1920, 1080, 32, 0.0, 32),
            (1920, 1080, 32, 0.02, 39),
            (1920, 1080, 20, 0.015, 29),
        ],
    )
    def test_effective_min_width(
        self, frame_width: int, frame_height: int, min_width_px: int, frac: float, expected: int
    ) -> None:
        """Verifica el cálculo del ancho mínimo efectivo."""
        result = effective_min_width(frame_width, frame_height, min_width_px, frac)
        assert result == expected


class TestCenterInRoi:
    """Tests de `center_in_roi`."""

    def test_center_in_roi_border_included(self) -> None:
        """Verifica que los bordes de la ROI se incluyen."""
        box = BoundingBox(0.0, 0.0, 100.0, 100.0)
        frame_width, frame_height = 1000, 1000

        # Centro en x = 50, y = 50
        assert center_in_roi(box, (0.05, 0.0, 1.0, 1.0), frame_width, frame_height)
        assert not center_in_roi(box, (0.051, 0.0, 1.0, 1.0), frame_width, frame_height)
        assert not center_in_roi(box, (0.0, 0.0, 1.0, 0.04), frame_width, frame_height)


class TestTouchesFrameEdge:
    """Tests parametrizados de `touches_frame_edge`."""

    @pytest.mark.parametrize(
        "box,frame_width,frame_height,expected",
        [
            (BoundingBox(2.0, 2.0, 638.0, 478.0), 640, 480, False),
            (BoundingBox(1.9, 10.0, 100.0, 50.0), 640, 480, True),
            (BoundingBox(10.0, 1.5, 100.0, 50.0), 640, 480, True),
            (BoundingBox(10.0, 10.0, 638.1, 50.0), 640, 480, True),
            (BoundingBox(10.0, 10.0, 100.0, 478.5), 640, 480, True),
        ],
    )
    def test_touches_frame_edge(
        self, box: BoundingBox, frame_width: int, frame_height: int, expected: bool
    ) -> None:
        """Verifica la detección de cajas que tocan el borde."""
        result = touches_frame_edge(box, frame_width, frame_height)
        assert result == expected


class TestValidateRoi:
    """Tests de `validate_roi`."""

    def test_validate_roi_valid(self) -> None:
        """Verifica que una ROI válida no lanza excepción."""
        validate_roi((0.0, 0.0, 1.0, 1.0))

    @pytest.mark.parametrize(
        "roi",
        [
            (0.5, 0.0, 0.4, 1.0),
            (0.0, 0.0, 1.0, 1.1),
            (-0.1, 0.0, 1.0, 1.0),
            (0.0, 0.5, 1.0, 0.5),
        ],
    )
    def test_validate_roi_invalid(self, roi: tuple[float, float, float, float]) -> None:
        """Verifica que ROIs inválidas lanzan ValueError con el mensaje exacto."""
        with pytest.raises(
            ValueError, match="roi inválida: se espera 0 <= x1 < x2 <= 1 y 0 <= y1 < y2 <= 1"
        ):
            validate_roi(roi)


class TestProcessingSettingsDefaults:
    """Tests de defaults y validación de `ProcessingSettings`."""

    def test_processing_settings_defaults_and_validation(self) -> None:
        """Verifica que los campos nuevos tienen los defaults correctos."""
        from lector_placas.application.process_video import ProcessingSettings
        from lector_placas.domain.errors import InvalidEntityError

        # Defaults correctos
        settings = ProcessingSettings("p", 8, 20, 0.0, 0.10, 2000, 8)
        assert settings.near_min_width_frac == 0.0
        assert settings.max_plate_vehicle_ratio == 1.0
        assert settings.roi == (0.0, 0.0, 1.0, 1.0)

        # Validaciones
        with pytest.raises(InvalidEntityError, match="near_min_width_frac debe estar en"):
            ProcessingSettings("p", 8, 20, 0.0, 0.10, 2000, 8, near_min_width_frac=0.3)
        with pytest.raises(InvalidEntityError, match="max_plate_vehicle_ratio debe estar en"):
            ProcessingSettings("p", 8, 20, 0.0, 0.10, 2000, 8, max_plate_vehicle_ratio=0.0)
        with pytest.raises(InvalidEntityError, match="roi inválida"):
            ProcessingSettings("p", 8, 20, 0.0, 0.10, 2000, 8, roi=(0.5, 0.0, 0.4, 1.0))


class TestProximityCounters:
    """Tests de la clase `ProximityCounters`."""

    def test_proximity_counters_defaults(self) -> None:
        """Verifica que todos los campos inicializan en 0."""
        counters = ProximityCounters()
        assert counters.outside_roi == 0
        assert counters.small_vehicle == 0
        assert counters.no_plate == 0
        assert counters.plate_at_edge == 0
        assert counters.narrow_plate == 0
        assert counters.blurry == 0
        assert counters.plate_outside_vehicle == 0


class TestCenterInBox:
    """Tests de `center_in_box`."""

    def test_center_inside(self) -> None:
        """El centro dentro de la caja cuenta como dentro."""
        outer = BoundingBox(0, 0, 100, 100)
        assert center_in_box(BoundingBox(10, 10, 20, 20), outer) is True

    def test_center_on_border_is_inside(self) -> None:
        """El centro sobre el borde cuenta como dentro."""
        outer = BoundingBox(0, 0, 100, 100)
        assert center_in_box(BoundingBox(90, 40, 110, 60), outer) is True

    def test_center_outside(self) -> None:
        """El centro fuera de la caja cuenta como fuera."""
        outer = BoundingBox(0, 0, 100, 100)
        assert center_in_box(BoundingBox(95, 40, 115, 60), outer) is False

    def test_only_center_matters(self) -> None:
        """Solo cuenta el centro, no el tamaño."""
        outer = BoundingBox(0, 0, 100, 100)
        assert center_in_box(BoundingBox(0, 0, 150, 150), outer) is True
