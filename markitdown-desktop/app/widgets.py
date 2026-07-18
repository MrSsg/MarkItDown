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
        logo.setStyleSheet("background: #6366F1; color: white; border-radius: 9px;")
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
        # Set PNG icons for tool buttons
        import os
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        icon_names = {"toolOpen": "open_file.png", "toolConvert": "Convert.png", "toolCopy": "copy.png", "toolClear": "delete.png"}
        for obj_id, fname in icon_names.items():
            if obj_id in self._tool_btns:
                fp = os.path.join(assets_dir, fname)
                if os.path.isfile(fp):
                    pixmap = QPixmap(fp)
                    if not pixmap.isNull():
                        self._tool_btns[obj_id].setIcon(QIcon(pixmap))
                        self._tool_btns[obj_id].setIconSize(QSize(20, 20))
                        self._tool_btns[obj_id].setText("")
        layout.addLayout(center)
        right = QHBoxLayout()
        right.setSpacing(4)
        self._theme_btn = QPushButton(chr(0x2600))
        fp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "theme.png")
        if os.path.isfile(fp):
            pix = QPixmap(fp)
            if not pix.isNull():
                self._theme_btn.setIcon(QIcon(pix))
                self._theme_btn.setIconSize(QSize(20, 20))
                self._theme_btn.setText("")
        self._theme_btn.setIconSize(QSize(20, 20))
        self._theme_btn.setText("")
        self._theme_btn.setObjectName("iconBtn")
        self._theme_btn.setFixedSize(38, 38)
        self._theme_btn.setToolTip("切换主题")
        right.addWidget(self._theme_btn)
        self._settings_btn = QPushButton(chr(0x2699))
        fp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "setting.png")
        if os.path.isfile(fp):
            pix = QPixmap(fp)
            if not pix.isNull():
                self._settings_btn.setIcon(QIcon(pix))
                self._settings_btn.setIconSize(QSize(20, 20))
                self._settings_btn.setText("")
        self._settings_btn.setIconSize(QSize(20, 20))
        self._settings_btn.setText("")
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
            'QLabel#UploadDropZone:hover { border-color: #6366F1; background: #F0F7FF; }'
        )
        self._drop_zone.setText(chr(0x1F4C4) + chr(32) + chr(25302) + chr(25341) + chr(25991) + chr(20214) + chr(21040) + chr(27492) + chr(22788) + chr(19978) + chr(20256))
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


        # --- Queue list ---
        self._queue_list = QListWidget()
        self._queue_list.setAlternatingRowColors(False)
        self._queue_list.setMinimumHeight(80)
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



# ---- Sidebar Navigation (v0.11.0) ----

class Sidebar(QFrame):
    nav_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(240)
        self.setStyleSheet("QFrame#Sidebar { background: #F5F5F5; border-right: 1px solid #E8E8E8; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("M")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(56)
        logo.setStyleSheet(
            "QLabel { background: #6366F1; color: white; font-size: 20px; font-weight: 700; "
            "border-radius: 0; }"
        )
        layout.addWidget(logo)

        # Nav items
        self._nav_btns = []
        items = [
            ("batch",   "\U0001f4e6 \u6279\u91cf\u8f6c\u6362"),
            ("history", "\U0001f4cb \u8f6c\u6362\u65e5\u5fd7"),
            ("settings","\u2699 \u8bbe\u7f6e"),
        ]
        for nav_id, label in items:
            btn = QPushButton(label)
            btn.setObjectName("NavItem_" + nav_id)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 0 16px; border: none; border-radius: 0; "
                "background: transparent; color: #4E5969; font-size: 14px; }"
                "QPushButton:hover { background: #E8E8E8; }"
            )
            btn.clicked.connect(lambda checked, nid=nav_id: self.nav_changed.emit(nid))
            layout.addWidget(btn)
            self._nav_btns.append((nav_id, btn))

        layout.addStretch()

    def set_active(self, nav_id):
        for nid, btn in self._nav_btns:
            if nid == nav_id:
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 0 16px; border: none; border-radius: 0; "
                    "border-left: 3px solid #6366F1; background: #EEF2FF; color: #6366F1; "
                    "font-size: 14px; font-weight: 600; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 0 16px; border: none; border-radius: 0; "
                    "background: transparent; color: #4E5969; font-size: 14px; }"
                    "QPushButton:hover { background: #E8E8E8; }"
                )


# ---- TopNavBar (v0.11.0 HTML spec) ----

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
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #222222; margin-left: 10px; margin-right: 40px;")
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
        self._theme_btn = QPushButton("\u263e")
        self._theme_btn.setFixedSize(28, 28)
        self._theme_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 16px; border-radius: 4px; } QPushButton:hover { background: #F5F5F5; }")
        layout.addWidget(self._theme_btn)
        self.set_active("file")

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
