# SPDX-License-Identifier: MIT
"""Widgets: TopBar, CollapsibleCard, DropArea, HistoryPanel."""

from PySide6.QtCore import Qt, QRect, QPoint, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QMenu, QApplication,
    QGraphicsDropShadowEffect)
from .theme import ThemeManager

TOPBAR_HEIGHT = 64
CARD_RADIUS = 16


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
        self._clayout.setSpacing(8)
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
        layout.setSpacing(8)

        # --- Drop zone ---
        self._drop_zone = QLabel()
        self._drop_zone.setObjectName("UploadDropZone")
        self._drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_zone.setMinimumHeight(90)
        self._drop_zone.setAcceptDrops(True)
        self._drop_zone.setStyleSheet(
            'QLabel#UploadDropZone { border: 2px dashed #C9CDD4; border-radius: 16px; background: #FAFBFC; color: #86909C; font-size: 13px; }'
            'QLabel#UploadDropZone:hover { border-color: #6366F1; background: #F0F7FF; }'
        )
        self._drop_zone.setText(chr(0x1F4C4) + chr(32) + chr(25302) + chr(25341) + chr(25991) + chr(20214) + chr(21040) + chr(27492) + chr(22788) + chr(19978) + chr(20256))
        layout.addWidget(self._drop_zone)

        # 文件类型图标（两行）
        def _mk_row(items):
            r = QHBoxLayout()
            r.setSpacing(8)
            r.addStretch()
            for lbl, bg in items:
                ft = QLabel(lbl)
                ft.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ft.setFixedSize(56, 26)
                ft.setStyleSheet(f"background: {bg}; color: white; border-radius: 6px; font-size: 10px; font-weight: 600;")
                r.addWidget(ft)
            r.addStretch()
            return r
        layout.addLayout(_mk_row([("PDF", "#F53F3F"), ("Word", "#2B6BEF"), ("PPT", "#FF7D00")]))
        layout.addLayout(_mk_row([("Excel", "#00B42A"), ("HTML", "#FF7D00"), ("EPUB", "#2B6BEF")]))

        # --- Queue list ---
        self._queue_list = QListWidget()
        self._queue_list.setAlternatingRowColors(False)
        self._queue_list.setMinimumHeight(60)
        self._queue_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._queue_list)



        # Drop zone events
        self._drop_zone.dragEnterEvent = self._on_drag_enter
        self._drop_zone.dragLeaveEvent = self._on_drag_leave
        self._drop_zone.dropEvent = self._on_drop
        self._drop_zone.mouseReleaseEvent = self._on_drop_zone_click

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
                  "converting": (chr(0x26A1) + " 转换中", "#6366F1"),
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

    # --- Click to select ---

    def _on_drop_zone_click(self, event):
        paths, _ = QFileDialog.getOpenFileNames(self, "\u9009\u62e9\u6587\u4ef6", "",
            "\u6240\u6709\u652f\u6301\u7684\u6587\u4ef6 (*.pdf *.docx *.pptx *.xlsx *.html *.txt *.csv *.md *.jpg *.png *.wav *.mp3);;\u6240\u6709\u6587\u4ef6 (*)")
        for p in paths:
            self.add_file(p)
        if paths:
            self.files_added.emit(paths)

    # --- Drop events ---

    def _on_drag_enter(self, event):
        if event.mimeData().hasUrls():
            self._drop_zone.setStyleSheet(
                'QLabel#UploadDropZone { border: 2px solid #6366F1; border-radius: 16px; background: #F0F7FF; color: #6366F1; font-size: 13px; }'
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
        self._count_lbl.setStyleSheet("color: #86909C; font-size: 12px;")
        hdr.addWidget(self._count_lbl)
        self._clear_btn = QPushButton("清空")
        self._clear_btn.setObjectName("histActionBtn")
        self._clear_btn.setStyleSheet("color: #F53F3F; background: transparent; border: none; padding: 4px 12px; font-size: 12px;")
        hdr.addWidget(self._clear_btn)
        layout.addLayout(hdr)
        self._list = QListWidget()
        self._list.setMinimumHeight(80)
        layout.addWidget(self._list, 1)

    @property
    def list_widget(self):
        return self._list
    @property
    def clear_btn(self):
        return self._clear_btn
    def set_count(self, n):
        self._count_lbl.setText(f"{n} records" if n else "")



# ---- Sidebar Navigation (v0.11.0) ----

class TopNavBar(QFrame):
    nav_changed = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopNavBar")
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("M")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6366F1,stop:1 #8B5CF6); color: white; font-size: 18px; font-weight: 700; border-radius: 8px;")
        layout.addWidget(logo)
        title = QLabel("MD\u5de5\u5177")
        title.setObjectName("navTitle")
        layout.addWidget(title)

        # Nav items
        layout.addSpacing(20)
        self._nav_btns = {}
        nav_items = [("file", "\u6587\u4ef6"), ("history", "\u5386\u53f2"), ("settings", "\u8bbe\u7f6e")]
        for nid, lbl in nav_items:
            btn = QPushButton(lbl)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { border: none; background: transparent; color: #666; font-size: 14px; padding: 0 16px; }"
                "QPushButton:hover { color: #6366F1; }"
            )
            btn.clicked.connect(lambda checked, i=nid: self.nav_changed.emit(i))
            layout.addWidget(btn)
            self._nav_btns[nid] = btn
        layout.addSpacing(24)

        # Action buttons
        self._import_btn = QPushButton("\u5bfc\u5165")
        self._import_btn.setStyleSheet("QPushButton { background: #6366F1; color: white; border: none; border-radius: 6px; padding: 6px 16px; font-size: 13px; } QPushButton:hover { background: #818CF8; }")
        layout.addWidget(self._import_btn)
        layout.addSpacing(8)

        self._batch_btn = QPushButton("\u6279\u91cf\u5bfc\u5165")
        self._batch_btn.setStyleSheet("QPushButton { background: transparent; color: #666; border: 1px solid #DDD; border-radius: 6px; padding: 6px 16px; font-size: 13px; } QPushButton:hover { border-color: #6366F1; color: #6366F1; }")
        layout.addWidget(self._batch_btn)
        layout.addSpacing(8)

        self._clear_btn = QPushButton("\u6e05\u7a7a")
        self._clear_btn.setStyleSheet("QPushButton { background: transparent; color: #EF4444; border: 1px solid #FECACA; border-radius: 6px; padding: 6px 16px; font-size: 13px; } QPushButton:hover { background: #FEF2F2; }")
        layout.addWidget(self._clear_btn)
        layout.addSpacing(8)

        self._copy_btn = QPushButton("\u590d\u5236MD")
        self._copy_btn.setStyleSheet("QPushButton { background: transparent; color: #666; border: 1px solid #DDD; border-radius: 6px; padding: 6px 16px; font-size: 13px; } QPushButton:hover { border-color: #6366F1; color: #6366F1; }")
        layout.addWidget(self._copy_btn)
        layout.addSpacing(8)

        self._export_btn = QPushButton("\u5bfc\u51fa")
        self._export_btn.setStyleSheet("QPushButton { background: transparent; color: #666; border: 1px solid #DDD; border-radius: 6px; padding: 6px 16px; font-size: 13px; } QPushButton:hover { border-color: #6366F1; color: #6366F1; }")
        layout.addWidget(self._export_btn)

        layout.addStretch()

        # Theme toggle
        self._theme_btn = QPushButton(chr(0x2600))
        self._theme_btn.setObjectName("iconBtn")
        self._theme_btn.setFixedSize(38, 38)
        self._theme_btn.setToolTip("切换主题")
        layout.addWidget(self._theme_btn)

    def update_theme_icon(self, is_dark):
        self._theme_btn.setText(chr(0x2600) if not is_dark else chr(0x263e))

    def set_active(self, nid):
        for anid, btn in self._nav_btns.items():
            if anid == nid:
                btn.setStyleSheet(
                    "QPushButton { border: none; background: transparent; color: #6366F1; font-weight: 600; font-size: 14px; padding: 0 16px; }"
                    "QPushButton:hover { color: #818CF8; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { border: none; background: transparent; color: #666; font-size: 14px; padding: 0 16px; }"
                    "QPushButton:hover { color: #6366F1; }"
                )
