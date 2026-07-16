# SPDX-License-Identifier: MIT
"""Widgets: TopBar, CollapsibleCard, DropArea, HistoryPanel."""

from PySide6.QtCore import Qt, QRect, QPoint, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QMenu, QApplication,
    QGraphicsDropShadowEffect)
from .theme import ThemeManager

TOPBAR_HEIGHT = 64
CARD_RADIUS = 16


class TopBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(TOPBAR_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)
        left = QHBoxLayout()
        left.setSpacing(6)
        logo = QLabel("MD")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        f = logo.font(); f.setBold(True); f.setPointSize(12)
        logo.setFont(f)
        logo.setStyleSheet("background: #407BFF; color: white; border-radius: 9px;")
        left.addWidget(logo)
        name_lbl = QLabel("MarkConvert Desk")
        name_lbl.setStyleSheet("font-size: 18px; font-weight: 600; padding: 0 4px;")
        left.addWidget(name_lbl)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: palette(mid);")
        left.addWidget(sep)
        for nav_id, txt in [("file", "  文件"), ("history", "  历史"), ("settings", "  设置")]:
            b = QPushButton(txt)
            b.setObjectName("navBtn")
            left.addWidget(b)
        left.addStretch()
        layout.addLayout(left, 1)
        center = QHBoxLayout()
        center.setSpacing(6)
        self._tool_btns = {}
        tool_defs = [
            ("toolOpen", chr(0x1F4C2) + " 打开"),
            ("toolConvert", chr(0x1F504) + " 转换"),
            ("toolCopy", chr(0x1F4CB) + " 复制"),
            ("toolMD", "MD"),
            ("toolClear", chr(0x1F5D1) + " 清空"),
        ]
        for obj_id, txt in tool_defs:
            b = QPushButton(txt)
            b.setObjectName("toolBtn")
            b.setFixedHeight(36)
            center.addWidget(b)
            self._tool_btns[obj_id] = b
        layout.addLayout(center)
        right = QHBoxLayout()
        right.setSpacing(4)
        self._theme_btn = QPushButton(chr(0x2600))
        self._theme_btn.setObjectName("iconBtn")
        self._theme_btn.setFixedSize(38, 38)
        self._theme_btn.setToolTip("切换主题")
        right.addWidget(self._theme_btn)
        self._settings_btn = QPushButton(chr(0x2699))
        self._settings_btn.setObjectName("iconBtn")
        self._settings_btn.setFixedSize(38, 38)
        self._settings_btn.setToolTip("设置")
        right.addWidget(self._settings_btn)
        layout.addLayout(right)

    def tool_button(self, name):
        return self._tool_btns.get(name)
    @property
    def theme_btn(self):
        return self._theme_btn
    @property
    def settings_btn(self):
        return self._settings_btn
    def update_theme_icon(self, is_dark):
        self._theme_btn.setText(chr(0x2602) if is_dark else chr(0x2600))


class CollapsibleCard(QFrame):
    def __init__(self, title="", parent=None, collapsed=False):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self._expanded = not collapsed
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        hdr = QWidget()
        hdr.setFixedHeight(52)
        hdr.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 12, 0)
        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("cardTitle")
        hl.addWidget(self._title_lbl)
        hl.addStretch()
        self._collapse_btn = QPushButton(chr(9660))
        self._collapse_btn.setObjectName("collapseBtn")
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.clicked.connect(self.toggle)
        hl.addWidget(self._collapse_btn)
        layout.addWidget(hdr)
        self._content = QWidget()
        self._content.setObjectName("cardContent")
        self._clayout = QVBoxLayout(self._content)
        self._clayout.setContentsMargins(20, 4, 20, 20)
        self._clayout.setSpacing(12)
        layout.addWidget(self._content)
        if collapsed:
            self._content.setVisible(False)

    def content_layout(self):
        return self._clayout
    def set_title(self, text):
        self._title_lbl.setText(text)
    def toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._collapse_btn.setText(chr(9650) if self._expanded else chr(9660))


class UploadPanel(QWidget):
    """Upload zone + file queue + action buttons."""

    files_added = Signal(list)
    convert_requested = Signal()
    clear_requested = Signal()
    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- Drop zone ---
        self._drop_zone = QLabel()
        self._drop_zone.setObjectName("UploadDropZone")
        self._drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_zone.setMinimumHeight(120)
        self._drop_zone.setAcceptDrops(True)
        self._drop_zone.setStyleSheet(
            'QLabel#UploadDropZone { border: 2px dashed #C9CDD4; border-radius: 16px; background: #FAFBFC; color: #86909C; font-size: 13px; }'
            'QLabel#UploadDropZone:hover { border-color: #407BFF; background: #F0F7FF; }'
        )
        self._drop_zone.setText(chr(0x1F4C2) + chr(10) + chr(10) + chr(25351) + chr(25512) + chr(25991) + chr(20214) + chr(21040) + chr(27492) + chr(22788) + chr(19978) + chr(20256))
        layout.addWidget(self._drop_zone)

        # --- File type icons row ---
        ft_row = QHBoxLayout()
        ft_row.setSpacing(8)
        ft_row.addStretch()
        for label, bg in [("PDF", "#F53F3F"), ("Word", "#2B6BEF"), ("PPT", "#FF7D00"),
                           ("Excel", "#00B42A"), ("图片", "#F53F3F"), ("HTML", "#FF7D00"),
                           ("EPUB", "#2B6BEF")]:
            ft = QLabel(label)
            ft.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ft.setFixedSize(56, 32)
            ft.setStyleSheet(f"background: {bg}; color: white; border-radius: 8px; font-size: 11px; font-weight: 600;")
            ft_row.addWidget(ft)
        ft_row.addStretch()
        layout.addLayout(ft_row)

        # --- Select file button ---
        self._select_btn = QPushButton(chr(0x1F4C2) + chr(32) + chr(36873) + chr(25321) + chr(25991) + chr(20214))
        self._select_btn.setObjectName("secondaryBtn")
        self._select_btn.setStyleSheet("QPushButton#secondaryBtn { background: #F2F3F5; color: #4E5969; border: 1px solid #E5E6EB; border-radius: 12px; padding: 8px 16px; }")
        layout.addWidget(self._select_btn)

        # --- Queue list ---
        self._queue_list = QListWidget()
        self._queue_list.setAlternatingRowColors(False)
        self._queue_list.setMinimumHeight(80)
        self._queue_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._queue_list)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._convert_btn = QPushButton(chr(0x1F680) + chr(32) + chr(19968) + chr(38190) + chr(36716) + chr(25442))
        self._convert_btn.setObjectName("primaryAction")
        self._convert_btn.setStyleSheet("QPushButton#primaryAction { background: #407BFF; color: white; font-size: 14px; font-weight: 600; padding: 10px 24px; }")
        self._new_btn = QPushButton(chr(0x2795) + chr(32) + chr(26032) + chr(24314) + chr(36716) + chr(25442))
        self._new_btn.setObjectName("secondaryBtn")
        btn_row.addWidget(self._convert_btn)
        btn_row.addWidget(self._new_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Drop zone events
        self._drop_zone.dragEnterEvent = self._on_drag_enter
        self._drop_zone.dragLeaveEvent = self._on_drag_leave
        self._drop_zone.dropEvent = self._on_drop

    # --- Queue management ---

    def add_file(self, filepath: str):
        import os
        name = os.path.basename(filepath)
        try: size = os.path.getsize(filepath)
        except: size = 0
        for u in ("B","KB","MB","GB"):
            if size < 1024: s = f"{size:.1f} {u}"; break
            size /= 1024
        item = QListWidgetItem()
        item.setText(f"  {name}  -  {s}")
        item.setData(Qt.UserRole, filepath)
        item.setData(Qt.UserRole + 1, "queued")
        self._queue_list.addItem(item)
        self._update_item_status(self._queue_list.count() - 1, "queued")

    def set_item_status(self, index, status):
        """status: queued, converting, success, error"""
        if 0 <= index < self._queue_list.count():
            self._update_item_status(index, status)

    def _update_item_status(self, idx, status):
        labels = {"queued": (chr(0x23F3) + " 排队中", "#86909C"),
                  "converting": (chr(0x26A1) + " 转换中", "#407BFF"),
                  "success": (chr(0x2705) + " 成功", "#00B42A"),
                  "error": (chr(0x274C) + " 失败", "#F53F3F")}
        text, color = labels.get(status, (status, "#86909C"))
        item = self._queue_list.item(idx)
        if item:
            item.setData(Qt.UserRole + 1, status)
            # Update display: append status badge
            base = item.text().split("  -")[0] if "  -" in item.text() else item.text()
            item.setText(f"{base}  [{text}]")
            item.setForeground(QColor(color))

    def clear_queue(self):
        self._queue_list.clear()

    def queue_count(self) -> int:
        return self._queue_list.count()

    def get_queue_paths(self) -> list:
        return [self._queue_list.item(i).data(Qt.UserRole)
                for i in range(self._queue_list.count())]

    # --- Item click ---

    def _on_item_clicked(self, item):
        path = item.data(Qt.UserRole)
        if path:
            self.file_selected.emit(path)

    # --- Drop events ---

    def _on_drag_enter(self, event):
        if event.mimeData().hasUrls():
            self._drop_zone.setStyleSheet(
                'QLabel#UploadDropZone { border: 2px solid #407BFF; border-radius: 16px; background: #F0F7FF; color: #407BFF; font-size: 13px; }'
            )
            event.acceptProposedAction()

    def _on_drag_leave(self, event):
        self._drop_zone.setStyleSheet(
            'QLabel#UploadDropZone { border: 2px dashed #C9CDD4; border-radius: 16px; background: #FAFBFC; color: #86909C; font-size: 13px; }'
        )

    def _on_drop(self, event):
        self._drop_zone.setStyleSheet(
            'QLabel#UploadDropZone { border: 2px dashed #C9CDD4; border-radius: 16px; background: #FAFBFC; color: #86909C; font-size: 13px; }'
        )
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.add_file(url.toLocalFile())
                paths.append(url.toLocalFile())
        if paths:
            self.files_added.emit(paths)
        event.acceptProposedAction()
class DropArea(QWidget):
    file_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropArea")
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self._drag_over = False
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        icon_lbl = QLabel(chr(0x1F4C1))
        icon_lbl.setObjectName("dropIcon")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)
        text_lbl = QLabel("拖拽文件到这里，或点击浏览")
        text_lbl.setObjectName("dropText")
        text_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(text_lbl)
        hint_lbl = QLabel("支持 PDF、DOCX、XLSX、PPTX、TXT、图片等多种格式")
        hint_lbl.setObjectName("dropHint")
        hint_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_lbl)
        self._browse_btn = QPushButton("浏览文件...")
        self._browse_btn.setObjectName("secondaryBtn")
        self._browse_btn.setFixedWidth(160)
        layout.addWidget(self._browse_btn, 0, Qt.AlignCenter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._drag_over = True
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_over = False
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self._drag_over = False
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.file_dropped.emit(paths)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            mw = self.window()
            if hasattr(mw, "_open_file"):
                mw._open_file()

    @property
    def browse_btn(self):
        return self._browse_btn

class HistoryPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        hdr = QHBoxLayout()
        title_lbl = QLabel("转换历史")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color: palette(mid); font-size: 12px;")
        hdr.addWidget(self._count_lbl)
        self._clear_btn = QPushButton("清空")
        self._clear_btn.setObjectName("histActionBtn")
        self._clear_btn.setStyleSheet("color: #F53F3F; background: transparent; border: none; padding: 4px 12px; font-size: 12px;")
        hdr.addWidget(self._clear_btn)
        layout.addLayout(hdr)
        self._list = QListWidget()
        self._list.setMinimumHeight(80)
        self._list.setMaximumHeight(160)
        layout.addWidget(self._list)

    @property
    def list_widget(self):
        return self._list
    @property
    def clear_btn(self):
        return self._clear_btn
    def set_count(self, n):
        self._count_lbl.setText(f"{n} records" if n else "")

