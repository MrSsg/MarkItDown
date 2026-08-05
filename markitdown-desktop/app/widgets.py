# SPDX-License-Identifier: MIT
"""Small reusable widgets. Visual styling belongs exclusively to theme QSS."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout


class HistoryPanel(QFrame):
    item_selected = Signal(object)
    item_activated = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        title = QLabel("转换历史")
        title.setObjectName("paneTitle")
        self._count = QLabel()
        self._count.setObjectName("mutedText")
        self._count.setAccessibleName("历史记录数量")
        self._clear = QPushButton("清空历史")
        self._clear.setObjectName("dangerBtn")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count)
        header.addWidget(self._clear)
        layout.addLayout(header)
        self._list = QListWidget()
        self._list.setAccessibleName("转换历史列表")
        self._list.currentItemChanged.connect(self._selection_changed)
        self._list.itemActivated.connect(self._activate_item)
        layout.addWidget(self._list)
        self._empty = QLabel("暂无转换记录\n完成一次转换后，记录会显示在这里。")
        self._empty.setObjectName("mutedText")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        layout.addWidget(self._empty)

    @property
    def list_widget(self):
        return self._list

    @property
    def clear_btn(self):
        return self._clear

    def set_count(self, count: int) -> None:
        self._count.setText(f"{count} 项" if count else "")
        self._empty.setVisible(count == 0)
        self._list.setVisible(count > 0)

    def _selection_changed(self, item, _previous) -> None:
        if item is not None:
            self.item_selected.emit(item)

    def _activate_item(self, item) -> None:
        if item is not None:
            self.item_activated.emit(item)
