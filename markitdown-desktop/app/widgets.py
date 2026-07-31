# SPDX-License-Identifier: MIT
"""Small reusable widgets. Visual styling belongs exclusively to theme QSS."""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout


class HistoryPanel(QFrame):
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
        self._clear = QPushButton("清空历史")
        self._clear.setObjectName("dangerBtn")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count)
        header.addWidget(self._clear)
        layout.addLayout(header)
        self._list = QListWidget()
        layout.addWidget(self._list)

    @property
    def list_widget(self):
        return self._list

    @property
    def clear_btn(self):
        return self._clear

    def set_count(self, count: int) -> None:
        self._count.setText(f"{count} 项" if count else "")
