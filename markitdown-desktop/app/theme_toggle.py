# SPDX-License-Identifier: MIT
"""Crisp, animated light/dark appearance toggle."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton, QStylePainter

from .theme import ThemeManager


class ThemeToggleButton(QPushButton):
    """A vector sun/moon control with a short cross-rotate transition."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_dark = False
        self._previous_is_dark = False
        self._transition = 1.0
        self._icon_color = QColor(ThemeManager.BRAND)
        self._motion_enabled = True
        self._animation = QPropertyAnimation(self, b"transition", self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setObjectName("themeToggle")
        self.setToolTip("切换浅色/深色主题")
        self.setAccessibleName("切换浅色或深色主题")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(36, 36)

    def get_transition(self) -> float:
        return self._transition

    def set_transition(self, value: float) -> None:
        self._transition = float(value)
        self.update()

    transition = Property(float, get_transition, set_transition)

    def set_theme(self, theme: str, animate: bool = True) -> None:
        is_dark = theme == "dark"
        if is_dark == self._is_dark:
            return
        self._previous_is_dark = self._is_dark
        self._is_dark = is_dark
        self._animation.stop()
        if animate and self._motion_enabled and self.isVisible():
            self.set_transition(0.0)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        else:
            self.set_transition(1.0)

    def set_accent_color(self, color: str) -> None:
        self._icon_color = QColor(color)
        self.update()

    def set_reduced_motion(self, reduced: bool) -> None:
        self._motion_enabled = not reduced

    def paintEvent(self, event) -> None:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        styled = QStylePainter(self)
        styled.drawControl(QStyle.ControlElement.CE_PushButton, option)
        styled.end()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        if self._transition < 1.0:
            self._paint_icon(painter, center, self._previous_is_dark, -70 * self._transition, 1.0 - self._transition)
            self._paint_icon(painter, center, self._is_dark, 80 * (1.0 - self._transition), self._transition)
        else:
            self._paint_icon(painter, center, self._is_dark, 0.0, 1.0)

    def _paint_icon(self, painter: QPainter, center, is_dark: bool, rotation: float, opacity: float) -> None:
        painter.save()
        painter.translate(center)
        painter.rotate(rotation)
        painter.setOpacity(opacity)
        color = self._icon_color
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if is_dark:
            moon = QPainterPath()
            moon.addEllipse(-7, -7, 14, 14)
            cutout = QPainterPath()
            cutout.addEllipse(-2, -9, 14, 14)
            painter.fillPath(moon.subtracted(cutout), color)
        else:
            painter.drawEllipse(-5, -5, 10, 10)
            for x1, y1, x2, y2 in ((0, -11, 0, -8), (0, 8, 0, 11), (-11, 0, -8, 0), (8, 0, 11, 0),
                                   (-7.8, -7.8, -5.8, -5.8), (7.8, 7.8, 5.8, 5.8),
                                   (-7.8, 7.8, -5.8, 5.8), (7.8, -7.8, 5.8, -5.8)):
                painter.drawLine(x1, y1, x2, y2)
        painter.restore()
