# SPDX-License-Identifier: MIT
"""Compact quick-import and batch-status window."""

from __future__ import annotations

import enum
import os

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QRectF, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget


SNAP_THRESHOLD = 20
UNSNAP_THRESHOLD = 50


class State(enum.Enum):
    COLLAPSED = 0
    HOVER = 1
    ACTIVE = 2


class DragBubble(QWidget):
    def __init__(self, theme_mgr):
        super().__init__(None)
        self._theme = theme_mgr
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = "拖放文件开始转换"
        fm = QFontMetrics(QFont("Microsoft YaHei", 10))
        self.setFixedSize(fm.horizontalAdvance(self._text) + 32, 44)
        self._theme.theme_changed.connect(self.update)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        painter.setClipPath(path)
        colors = self._theme.colors
        bg = QColor(colors.card_bg)
        bg.setAlpha(245)
        painter.fillRect(self.rect(), bg)
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 14, 14)
        painter.setPen(QColor(colors.primary_text))
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

    def show_near(self, float_geo, edge, screen_geo):
        bw, bh = self.width(), self.height()
        sp = 12
        cx = float_geo.center().x()
        x = max(screen_geo.left() + 5, min(cx - bw // 2, screen_geo.right() - bw - 5))
        if float_geo.top() - sp - bh >= screen_geo.top() + 5:
            y = float_geo.top() - sp - bh
        else:
            y = float_geo.bottom() + sp
        y = max(screen_geo.top() + 5, min(y, screen_geo.bottom() - bh - 5))
        self.move(x, y)
        self.show()


class FloatWindow(QWidget):
    file_dropped = Signal(str)
    import_requested = Signal()
    show_main_requested = Signal()
    show_settings_requested = Signal()
    status_summary_changed = Signal(str)

    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._theme = theme_mgr
        self._state = State.COLLAPSED
        self._edge: str | None = None
        self._drag_start: QPoint | None = None
        self._drag_orig: QPoint | None = None
        self._hovered = False
        self._dragging = False
        self._file_drag_active = False
        self._pre_drag_summary = ""
        self._status_summary = "就绪"
        self._motion_enabled = not settings.reduce_motion
        self._scaled_icon_cache: dict[tuple[str, int], QPixmap] = {}

        self._bubble = DragBubble(theme_mgr)
        self._bubble_hide_timer = QTimer(self)
        self._bubble_hide_timer.setSingleShot(True)
        self._bubble_hide_timer.timeout.connect(self._hide_bubble)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._on_collapse_timeout)
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._load_icons()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAccessibleName("MarkItDownDesk 快捷悬浮窗")
        self.setToolTip("拖放文件开始转换；双击打开主窗口")
        self.setAcceptDrops(True)

        self._summary_label = QLabel(self)
        self._summary_label.setObjectName("floatSummary")
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setAccessibleName("悬浮窗任务摘要")
        self._summary_label.setText(self._status_summary)
        self._open_button = QPushButton("打开主窗口", self)
        self._open_button.setObjectName("floatAction")
        self._open_button.clicked.connect(self.show_main_requested.emit)
        self._import_button = QPushButton("导入文件", self)
        self._import_button.setObjectName("floatAction")
        self._import_button.clicked.connect(self.import_requested.emit)
        self._set_controls_visible(State.COLLAPSED)

        self._restore_position()
        self._theme.theme_changed.connect(self._on_theme_changed)

    def _load_icons(self):
        directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        svg_path = os.path.join(directory, "markconvert_float.svg")
        self._icon_renderer = QSvgRenderer(svg_path) if os.path.isfile(svg_path) else None
        self._icons: dict[int, QPixmap] = {}
        for size in (16, 32, 128, 256, 512):
            path = os.path.join(directory, f"markconvert_float_{size}.png")
            if os.path.isfile(path):
                self._icons[size] = QPixmap(path)

    def _on_theme_changed(self, _theme):
        self._scaled_icon_cache.clear()
        self._bubble.update()
        self.update()

    def set_reduced_motion(self, reduced: bool) -> None:
        self._motion_enabled = not reduced

    def set_status_summary(self, summary: str) -> None:
        self._status_summary = summary or "就绪"
        self._summary_label.setText(self._status_summary)
        self.status_summary_changed.emit(self._status_summary)

    def set_history_entries(self, entries):
        # Kept for the tray/bootstrap compatibility path; the main window owns history details.
        self._history_count = len(entries or [])

    def _set_controls_visible(self, state: State) -> None:
        self._summary_label.setVisible(state != State.COLLAPSED)
        self._open_button.setVisible(state == State.ACTIVE)
        self._import_button.setVisible(state == State.ACTIVE)

    def _show_bubble(self):
        # Drag feedback is rendered inside the expandable window; never create
        # a second top-level mask over the user's workspace.
        self._bubble.hide()

    def _hide_bubble(self):
        self._bubble.hide()

    def _animate_to(self, target: QRect, duration: int = 180):
        self._animation.stop()
        self._animation.setDuration(duration if self._motion_enabled else 0)
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(target)
        self._animation.start()

    def set_state(self, state: State):
        if state == self._state:
            self._set_controls_visible(state)
            return
        self._state = state
        self._set_controls_visible(state)
        self._animate_to(self._compute_rect(state))
        # The collapsed state remains a valid drop target for quick import.
        self.setAcceptDrops(True)
        self.update()

    def _compute_rect(self, state: State) -> QRect:
        screen = self._current_screen_geo()
        if screen is None:
            return self.geometry()
        sizes = {State.COLLAPSED: (48, 48), State.HOVER: (72, 200), State.ACTIVE: (280, 238)}
        width, height = sizes[state]
        cx, cy = self.geometry().center().x(), self.geometry().center().y()
        if self._edge is None:
            x = max(screen.left(), min(cx - width // 2, screen.right() - width + 1))
            y = max(screen.top(), min(cy - height // 2, screen.bottom() - height + 1))
            return QRect(x, y, width, height)
        if self._edge == "left":
            y = max(screen.top(), min(cy - height // 2, screen.bottom() - height))
            return QRect(screen.left(), y, width, height)
        if self._edge == "right":
            y = max(screen.top(), min(cy - height // 2, screen.bottom() - height))
            return QRect(screen.right() - width + 1, y, width, height)
        if self._edge == "top":
            x = max(screen.left(), min(cx - width // 2, screen.right() - width))
            return QRect(x, screen.top(), width, height)
        if self._edge == "bottom":
            x = max(screen.left(), min(cx - width // 2, screen.right() - width))
            return QRect(x, screen.bottom() - height + 1, width, height)
        return self.geometry()

    def _current_screen_geo(self):
        screen = self.screen()
        return screen.geometry() if screen else None

    def _restore_position(self):
        edge = self._settings.float_edge
        pos = self._settings.float_position
        if edge:
            self._edge = edge
            self.setGeometry(self._compute_rect(State.COLLAPSED))
        elif pos:
            self.setGeometry(QRect(pos.x(), pos.y(), 48, 48))
        else:
            screen = self._current_screen_geo()
            if screen:
                self.setGeometry(screen.right() - 64, screen.bottom() - 96, 48, 48)
            else:
                self.resize(48, 48)

    def _check_edge_snap(self, allow_snap=True):
        center = self.geometry().center()
        best_edge = None
        best_dist = SNAP_THRESHOLD + 1
        for screen in QApplication.screens():
            geometry = screen.geometry()
            for edge, distance in (
                ("left", abs(center.x() - geometry.left())),
                ("right", abs(center.x() - geometry.right())),
                ("top", abs(center.y() - geometry.top())),
                ("bottom", abs(center.y() - geometry.bottom())),
            ):
                if distance < best_dist:
                    best_dist, best_edge = distance, edge
        if best_edge is not None and best_dist <= SNAP_THRESHOLD:
            if not allow_snap:
                return False
            self._edge = best_edge
            self.set_state(State.COLLAPSED)
            return True
        if self._edge is not None:
            center_x, center_y = self.geometry().center().x(), self.geometry().center().y()
            screen = self._current_screen_geo()
            if screen:
                distance = {
                    "left": abs(center_x - screen.left()),
                    "right": abs(center_x - screen.right()),
                    "top": abs(center_y - screen.top()),
                    "bottom": abs(center_y - screen.bottom()),
                }[self._edge]
                if distance > UNSNAP_THRESHOLD:
                    self._edge = None
        return False

    def _start_collapse_timer(self):
        self._collapse_timer.start(self._settings.collapse_delay)

    def _stop_collapse_timer(self):
        self._collapse_timer.stop()

    def _on_collapse_timeout(self):
        if not self._dragging and not self._hovered:
            self.set_state(State.COLLAPSED)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_orig = self.geometry().topLeft()
            self._dragging = True
            self._stop_collapse_timer()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_orig + delta)
            self._check_edge_snap(allow_snap=False)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self._drag_orig = None
            self._dragging = False
            self._check_edge_snap()
            self._settings.float_position = self.geometry().topLeft()
            self._settings.float_edge = self._edge
            self._settings.sync()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_main_requested.emit()

    def enterEvent(self, event):
        self._hovered = True
        self._stop_collapse_timer()
        if self._state == State.COLLAPSED:
            self.set_state(State.HOVER)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._start_collapse_timer()
        self.update()
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._file_drag_active = True
            self._pre_drag_summary = self._status_summary
            self._summary_label.setText("松开鼠标以导入文件")
            self.set_state(State.ACTIVE)
            self._stop_collapse_timer()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._file_drag_active = False
        self._summary_label.setText(self._pre_drag_summary or self._status_summary)
        self._bubble_hide_timer.stop()
        self._hide_bubble()
        self._start_collapse_timer()
        self.update()

    def dropEvent(self, event):
        self._file_drag_active = False
        self._summary_label.setText(self._pre_drag_summary or self._status_summary)
        self._bubble_hide_timer.stop()
        self._hide_bubble()
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
        self.show_main_requested.emit()
        event.acceptProposedAction()
        self._start_collapse_timer()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.show_main_requested.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.set_state(State.COLLAPSED)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        show = QAction("显示主窗口", self)
        show.triggered.connect(self.show_main_requested.emit)
        menu.addAction(show)
        import_action = QAction("导入文件", self)
        import_action.triggered.connect(self.import_requested.emit)
        menu.addAction(import_action)
        menu.addSeparator()
        theme = QAction("切换主题", self)
        theme.triggered.connect(self._theme.toggle)
        menu.addAction(theme)
        settings = QAction("设置", self)
        settings.triggered.connect(self.show_settings_requested.emit)
        menu.addAction(settings)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def resizeEvent(self, event):
        margin = 14
        icon_offset = 52
        button_width = max(10, self.width() - margin * 2)
        if self._state == State.ACTIVE:
            open_y = max(icon_offset + 76, self.height() - 40)
            import_y = max(icon_offset + 42, open_y - 36)
            summary_height = max(36, import_y - icon_offset - 8)
            self._summary_label.setGeometry(margin, icon_offset, button_width, summary_height)
            self._import_button.setGeometry(margin, import_y, button_width, 28)
            self._open_button.setGeometry(margin, open_y, button_width, 28)
        else:
            self._summary_label.setGeometry(
                margin, icon_offset, button_width, max(36, self.height() - icon_offset - 12)
            )
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), 14, 14)
        painter.setClipPath(path)
        colors = self._theme.colors
        background = QColor(colors.card_bg)
        background.setAlpha(248)
        painter.fillRect(rect, background)
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawRoundedRect(0, 0, rect.width() - 1, rect.height() - 1, 14, 14)
        self._draw_png_icon(painter, rect.width(), 34 if self._state == State.COLLAPSED else 36)

    def _draw_png_icon(self, painter, width: int, size: int):
        if self._icon_renderer and self._icon_renderer.isValid():
            x = (width - size) / 2
            y = (self.height() - size) / 2 if self._state == State.COLLAPSED else 6
            self._icon_renderer.render(painter, QRectF(x, y, size, size))
            return
        pixmap = self._icons.get(128) or self._icons.get(32)
        if not pixmap:
            return
        theme = self._theme.current_theme
        key = (theme, size)
        scaled = self._scaled_icon_cache.get(key)
        if scaled is None:
            scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._scaled_icon_cache[key] = scaled
        x = (width - scaled.width()) // 2
        painter.drawPixmap(x, 4 if self._state != State.COLLAPSED else (self.height() - scaled.height()) // 2, scaled)
