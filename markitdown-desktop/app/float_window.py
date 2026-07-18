# SPDX-License-Identifier: MIT

import enum
from PySide6.QtCore import (Qt, QRect, QPoint, QRectF, QTimer, Signal, QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QFont, QFontMetrics, QAction, QPen, QPixmap, QIcon, QRadialGradient, QBrush)
from PySide6.QtWidgets import QWidget, QApplication, QMenu
from .theme import ThemeManager

SNAP_THRESHOLD = 20
UNSNAP_THRESHOLD = 50


class State(enum.Enum):
    COLLAPSED = 0
    HOVER = 1
    ACTIVE = 2





class DragBubble(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = "\U0001f4c4 \u62d6\u62fd\u6587\u4ef6\u5230\u6b64\u5f00\u59cb\u8f6c\u6362"
        fm = QFontMetrics(QFont("Segoe UI", 10))
        self.setFixedSize(fm.horizontalAdvance(self._text) + 32, 44)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 14, 14)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor(0, 0, 0, 200))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 14, 14)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

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
    show_main_requested = Signal()
    show_settings_requested = Signal()

    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._theme = theme_mgr
        self._state = State.COLLAPSED
        self._edge = None
        self._drag_start = None
        self._drag_orig = None
        self._history_entries = []

        self._bubble = DragBubble()  # single instance
        self._hovered = False
        self._dragging = False
        self._file_drag_active = False
        self._bubble_hide_timer = QTimer(self)
        self._bubble_hide_timer.setSingleShot(True)
        self._bubble_hide_timer.timeout.connect(self._hide_bubble)
        self._load_icons()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._on_collapse_timeout)

        self._restore_position()
        self._theme.theme_changed.connect(self.update)

    def _load_icons(self):
        import os
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        self._fp = {}
        for s in [16, 32, 128, 256, 512]:
            p = os.path.join(d, "markconvert_float_" + str(s) + ".png")
            if os.path.isfile(p):
                self._fp[s] = QPixmap(p)

    def _show_bubble(self):
        if hasattr(self, "_bubble_hide_timer"):
            self._bubble_hide_timer.stop()
        if not self._bubble.isVisible():
            sg = self.screen().geometry() if self.screen() else None
            if sg:
                self._bubble.show_near(self.geometry(), self._edge, sg)

    def _hide_bubble(self):
        if self._bubble.isVisible():
            self._bubble.hide()

    def set_history_entries(self, entries):
        self._history_entries = entries
        if self._state == State.ACTIVE:
            self.update()

    def _animate_to(self, target, duration=220):
        a = QPropertyAnimation(self, b"geometry")
        a.setDuration(duration)
        a.setStartValue(self.geometry())
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        return a

    def set_state(self, state):
        if state == self._state:
            return
        self._state = state
        self._animate_to(self._compute_rect(state))
        self.setAcceptDrops(state != State.COLLAPSED)

    def _compute_rect(self, state):
        if self._edge is None:
            return self.geometry()
        screen = self._current_screen_geo()
        if screen is None:
            return self.geometry()
        sizes = {State.COLLAPSED: (36, 36), State.HOVER: (64, 180), State.ACTIVE: (260, 380)}
        w, h = sizes[state]
        cx, cy = self.geometry().center().x(), self.geometry().center().y()
        if self._edge == "left":
            y = max(screen.top(), min(cy - h // 2, screen.bottom() - h))
            return QRect(screen.left(), y, w, h)
        elif self._edge == "right":
            y = max(screen.top(), min(cy - h // 2, screen.bottom() - h))
            return QRect(screen.right() - w + 1, y, w, h)
        elif self._edge == "top":
            x = max(screen.left(), min(cx - w // 2, screen.right() - w))
            return QRect(x, screen.top(), w, h)
        elif self._edge == "bottom":
            x = max(screen.left(), min(cx - w // 2, screen.right() - w))
            return QRect(x, screen.bottom() - h + 1, w, h)
        return self.geometry()

    def _current_screen_geo(self):
        s = self.screen()
        return s.geometry() if s else None

    def _restore_position(self):
        edge = self._settings.float_edge
        pos = self._settings.float_position
        if edge:
            self._edge = edge
            self.setGeometry(self._compute_rect(State.COLLAPSED))
        elif pos:
            self.setGeometry(QRect(pos.x(), pos.y(), 36, 36))
        else:
            sg = self._current_screen_geo()
            if sg:
                self.setGeometry(sg.right() - 56, sg.bottom() - 80, 36, 36)
            else:
                self.resize(36, 36)

    def _check_edge_snap(self, allow_snap=True):
        screens = QApplication.screens()
        center = self.geometry().center()
        best_edge = None
        best_dist = SNAP_THRESHOLD + 1
        for screen in screens:
            g = screen.geometry()
            for en, d in [("left", abs(center.x() - g.left())), ("right", abs(center.x() - g.right())),
                          ("top", abs(center.y() - g.top())), ("bottom", abs(center.y() - g.bottom()))]:
                if d < best_dist:
                    best_dist, best_edge = d, en
        if best_edge is not None and best_dist <= SNAP_THRESHOLD:
            if not allow_snap:
                return False
            self._edge = best_edge
            self._animate_to(self._compute_rect(State.COLLAPSED), 180)
            self._state = State.COLLAPSED
            return True
        if self._edge is not None:
            cx, cy = self.geometry().center().x(), self.geometry().center().y()
            sg = self._current_screen_geo()
            if sg:
                d = {"left": abs(cx - sg.left()), "right": abs(cx - sg.right()),
                     "top": abs(cy - sg.top()), "bottom": abs(cy - sg.bottom())}[self._edge]
                if d > UNSNAP_THRESHOLD:
                    self._edge = None
        return False

    def _start_collapse_timer(self):
        self._collapse_timer.start(self._settings.collapse_delay)

    def _stop_collapse_timer(self):
        self._collapse_timer.stop()

    def _on_collapse_timeout(self):
        if self._edge is not None and self._state != State.COLLAPSED:
            self.set_state(State.COLLAPSED)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_orig = self.geometry().topLeft()
            self._dragging = True
            self._stop_collapse_timer()


    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_orig + delta)
            self._check_edge_snap(allow_snap=False)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self._drag_orig = None
            self._dragging = False
            self.update()
            self._check_edge_snap()
            if self._edge is not None:
                self.set_state(State.COLLAPSED)
            self._settings.float_position = self.geometry().topLeft()
            self._settings.float_edge = self._edge
            self._settings.sync()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_main_requested.emit()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        self._stop_collapse_timer()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        if self._edge is not None:
            self._start_collapse_timer()



    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._file_drag_active = True
            self._show_bubble()
            self._stop_collapse_timer()
            event.acceptProposedAction()
            self.update()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._file_drag_active = False
        self._bubble_hide_timer.stop()
        self._hide_bubble()
        self._bubble_hide_timer.start(200)
        self._start_collapse_timer()
        self.update()

    def dropEvent(self, event):
        self._file_drag_active = False
        self._bubble_hide_timer.stop()
        self._hide_bubble()
        self._bubble_hide_timer.start(200)
        self._start_collapse_timer()
        self.show_main_requested.emit()
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
        event.acceptProposedAction()
        if self._edge is not None:
            self._start_collapse_timer()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        a = QAction("显示主窗口", self); a.triggered.connect(self.show_main_requested.emit); menu.addAction(a)
        menu.addSeparator()
        a = QAction("切换主题", self); a.triggered.connect(lambda: self._theme.toggle()); menu.addAction(a)
        a = QAction("设置", self); a.triggered.connect(self.show_settings_requested.emit); menu.addAction(a)
        menu.addSeparator()
        a = QAction("退出", self); a.triggered.connect(QApplication.quit); menu.addAction(a)
        menu.exec(event.globalPos())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r, w, h = self.rect(), self.rect().width(), self.rect().height()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 14, 14)
        painter.setClipPath(path)
        # COLLAPSED: only icon PNG, no background fill or border
        if self._state != State.COLLAPSED:
            is_dark = self._theme.current_theme == "dark"
            bg = QColor("#2d2d2d") if is_dark else QColor("#ffffff")
            painter.fillRect(r, bg)
            bw = 1
            bc = QColor("#555" if is_dark else "#ccc")
            painter.setPen(QPen(bc, bw))
            painter.drawRoundedRect(0, 0, w - 1, h - 1, 14, 14)
        self._draw_png_icon(painter, w, h, min(w, h) - 8)

    def _draw_png_icon(self, painter, w, target_h, sz):
        cx, cy = w // 2, target_h // 2
        pm = self._fp.get(128) or self._fp.get(32)
        if pm:
            sc = pm.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (w - sc.width()) // 2
            y = (target_h - sc.height()) // 2
            painter.drawPixmap(x, y, sc)


