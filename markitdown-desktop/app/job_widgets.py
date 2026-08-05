# SPDX-License-Identifier: MIT
"""Queue view used by the professional two-pane workspace."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem, QStyle

from .jobs import JobItem


class JobList(QListWidget):
    item_selected = Signal(str)
    item_activated = Signal(str)

    _STATE_LABELS = {
        "queued": "等待中",
        "running": "转换中",
        "success": "已完成",
        "error": "失败",
        "cancelled": "已取消",
    }
    _STATE_ICONS = {
        "queued": "SP_ArrowRight",
        "running": "SP_BrowserReload",
        "success": "SP_DialogApplyButton",
        "error": "SP_MessageBoxCritical",
        "cancelled": "SP_DialogCancelButton",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("任务队列")
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.currentItemChanged.connect(self._selection_changed)
        self.itemActivated.connect(self._activate_item)
        self._empty_label = QLabel("暂无任务\n添加文件后会显示在这里", self.viewport())
        self._empty_label.setObjectName("queueEmptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_label.hide()

    @property
    def empty_label(self) -> QLabel:
        return self._empty_label

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._empty_label.setGeometry(self.viewport().rect())

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if not self.count():
            hint.setHeight(110)
        return hint

    def _selection_changed(self, item, _previous) -> None:
        if item is not None:
            self.item_selected.emit(str(item.data(Qt.UserRole)))

    def _activate_item(self, item) -> None:
        if item is not None:
            self.item_activated.emit(str(item.data(Qt.UserRole)))

    def refresh(self, items: list[JobItem]) -> None:
        selected = self.currentItem().data(Qt.UserRole) if self.currentItem() else None
        self.clear()
        if not items:
            self._empty_label.show()
            self._empty_label.raise_()
            return
        self._empty_label.hide()
        for item in items:
            state_label = self._STATE_LABELS.get(item.state, "等待中")
            label = f"{state_label}  {os.path.basename(item.file_path)}"
            if item.failure:
                label += f"\n{item.failure.message}"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item.file_path)
            row.setData(Qt.UserRole + 1, item.state)
            row.setData(Qt.UserRole + 2, state_label)
            row.setToolTip(f"{state_label}: {os.path.basename(item.file_path)}")
            icon_name = self._STATE_ICONS.get(item.state, "SP_FileIcon")
            icon_type = getattr(QStyle, icon_name, QStyle.StandardPixmap.SP_FileIcon)
            row.setIcon(QApplication.style().standardIcon(icon_type))
            self.addItem(row)
            if item.file_path == selected:
                self.setCurrentItem(row)
        if self.count() and self.currentItem() is None:
            self.setCurrentRow(0)
