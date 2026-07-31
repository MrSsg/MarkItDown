# SPDX-License-Identifier: MIT
"""Queue view used by the professional two-pane workspace."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .jobs import JobItem


class JobList(QListWidget):
    item_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.itemClicked.connect(lambda item: self.item_selected.emit(item.data(Qt.UserRole)))

    def refresh(self, items: list[JobItem]) -> None:
        selected = self.currentItem().data(Qt.UserRole) if self.currentItem() else None
        self.clear()
        for item in items:
            prefix = {"queued": "○", "running": "◌", "success": "✓", "error": "!", "cancelled": "–"}.get(item.state, "○")
            label = f"{prefix}  {os.path.basename(item.file_path)}"
            if item.failure:
                label += f"\n    {item.failure.message}"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item.file_path)
            row.setData(Qt.UserRole + 1, item.state)
            self.addItem(row)
            if item.file_path == selected:
                self.setCurrentItem(row)
