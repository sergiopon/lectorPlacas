from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView

from lector_placas.gui.widgets import NoCopyTableView


class _SimpleModel(QAbstractTableModel):
    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 2

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 2

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            return f"r{index.row()}c{index.column()}"
        return None


def _view() -> NoCopyTableView:
    view = NoCopyTableView()
    view.setModel(_SimpleModel(view))
    return view


def test_no_context_menu_and_no_edit(qapp) -> None:
    view = _view()
    assert view.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu
    assert view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert view.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows


def test_copy_shortcut_does_not_touch_clipboard(qapp) -> None:
    view = _view()
    view.setCurrentIndex(view.model().index(0, 0))
    view.show()
    sentinel = "centinela-no-se-toca"
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(sentinel)
    QTest.keySequence(view, QKeySequence.StandardKey.Copy)
    assert clipboard.text() == sentinel
    view.close()
