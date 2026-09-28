"""Tema visual claro y hoja de estilo de la GUI (spec 047, ADR-015)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from PySide6.QtWidgets import QApplication

from lector_placas.domain.entities import ReviewStatus

ACCENT: Final[str] = "#2563EB"
BACKGROUND: Final[str] = "#F5F6F8"
SURFACE: Final[str] = "#FFFFFF"
BORDER: Final[str] = "#E1E4E8"
TEXT: Final[str] = "#1F2328"
MUTED: Final[str] = "#656D76"
PLATE_YELLOW: Final[str] = "#FFD500"

STATUS_COLORS: Final[Mapping[ReviewStatus, tuple[str, str]]] = MappingProxyType(
    {
        ReviewStatus.UNVERIFIED: ("#92400E", "#FEF3C7"),
        ReviewStatus.CONFIRMED: ("#166534", "#DCFCE7"),
        ReviewStatus.CORRECTED: ("#1E40AF", "#DBEAFE"),
        ReviewStatus.REJECTED: ("#991B1B", "#FEE2E2"),
        ReviewStatus.ILLEGIBLE: ("#374151", "#F3F4F6"),
    }
)

_ACCENT_HOVER: Final[str] = "#1D4ED8"
_ACCENT_DISABLED: Final[str] = "#A9BEF2"
_ON_ACCENT: Final[str] = "#FFFFFF"

STYLESHEET: Final[str] = "".join(
    (
        f"QMainWindow, QDialog {{ background: {BACKGROUND}; }}\n",
        f"QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};"
        f" border-radius: 6px; padding: 6px 14px; }}\n",
        f'QPushButton[role="primary"] {{ background: {ACCENT}; color: {_ON_ACCENT};'
        f" border: none; }}\n",
        f'QPushButton[role="primary"]:hover {{ background: {_ACCENT_HOVER}; }}\n',
        f'QPushButton[role="primary"]:disabled {{ background: {_ACCENT_DISABLED}; }}\n',
        f'QPushButton[role="ghost"] {{ background: transparent; border: none;'
        f" color: {ACCENT}; }}\n",
        f"QLineEdit, QComboBox, QSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: 6px; padding: 4px 8px; }}\n",
        f"QProgressBar {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: 6px; }}\n",
        f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}\n",
        f'QLabel[role="title"] {{ color: {TEXT}; font-size: 20px; font-weight: bold; }}\n',
        f'QLabel[role="muted"] {{ color: {MUTED}; }}\n',
        f"QFrame#PlateCard {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: 10px; }}\n",
        f'QFrame#PlateCard[selected="true"] {{ border: 2px solid {ACCENT}; }}\n',
        f"QLabel#PlateText {{ background: {PLATE_YELLOW}; color: {TEXT};"
        f" border: 2px solid {TEXT}; border-radius: 4px; font-family: monospace;"
        f" font-weight: bold; font-size: 22px; padding: 2px 10px; }}\n",
    )
)


def apply_theme(app: QApplication) -> None:
    """Aplica el estilo Fusion y la hoja de estilo del tema a `app`.

    No lee ni escribe archivos ni persiste estado (SEG-27).

    Args:
        app: aplicación Qt ya creada.
    """
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
