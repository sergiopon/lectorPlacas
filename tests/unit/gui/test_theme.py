from __future__ import annotations

from lector_placas.domain.entities import ReviewStatus
from lector_placas.gui.theme import ACCENT, PLATE_YELLOW, STATUS_COLORS, STYLESHEET, apply_theme


def test_status_colors_cover_all_statuses() -> None:
    for status in ReviewStatus:
        colors = STATUS_COLORS[status]
        assert len(colors) == 2
        assert all(isinstance(color, str) and color for color in colors)


def test_stylesheet_uses_palette() -> None:
    assert ACCENT in STYLESHEET
    assert PLATE_YELLOW in STYLESHEET
    assert "#PlateCard" in STYLESHEET
    assert "PlateText" in STYLESHEET


def test_apply_theme_sets_stylesheet_and_fusion(qapp) -> None:
    previous = qapp.styleSheet()
    try:
        apply_theme(qapp)
        assert qapp.styleSheet() == STYLESHEET
        # Con una hoja de estilo puesta, Qt envuelve el estilo base en un QStyleSheetStyle
        # anónimo; se retira la hoja para observar el estilo base que quedó activo.
        qapp.setStyleSheet("")
        assert qapp.style().objectName().lower() == "fusion"
    finally:
        qapp.setStyleSheet(previous)
