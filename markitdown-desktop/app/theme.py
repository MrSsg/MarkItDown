# SPDX-License-Identifier: MIT

import os, sys
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

def _resource_path(relative: str) -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

class ThemeColors:
    """Holds the full color palette for one theme (light or dark)."""
    def __init__(self, is_dark: bool):
        if is_dark:
            self.bg = "#12141A"
            self.card_bg = "#1C1F28"
            self.card_hover = "#272B36"
            self.primary_text = "#F5F7FA"
            self.body_text = "#C9CDD4"
            self.secondary_text = "#86909C"
            self.border = "#303643"
            self.accent_border = "#407BFF50"
            self.topbar_bg = "#1C1F28"
        else:
            self.bg = "#F7F8FC"
            self.card_bg = "#FFFFFF"
            self.card_hover = "#F2F5FF"
            self.primary_text = "#1D2129"
            self.body_text = "#4E5969"
            self.secondary_text = "#86909C"
            self.border = "#E5E6EB"
            self.accent_border = "#407BFF40"
            self.topbar_bg = "#FFFFFF"

class ThemeManager(QObject):
    theme_changed = Signal(str)

    BRAND = "#407BFF"
    SUCCESS = "#00B42A"
    WARNING = "#FF7D00"
    ERROR = "#F53F3F"
    DISABLED = "#86909C"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "system"
        self._current = "light"
        self._colors = ThemeColors(False)
        hints = QApplication.styleHints()
        try:
            hints.colorSchemeChanged.connect(self._on_scheme_changed)
        except AttributeError:
            pass

    @property
    def mode(self): return self._mode
    @property
    def current_theme(self): return self._current
    @property
    def colors(self): return self._colors

    def set_mode(self, mode):
        self._mode = mode
        if mode == "system":
            self._apply_system_theme()
        else:
            self._apply(mode)

    def toggle(self):
        new = "dark" if self._current == "light" else "light"
        self._mode = new
        self._apply(new)

    def apply(self):
        if self._mode == "system":
            self._apply_system_theme()
        else:
            self._apply(self._mode)

    def _apply_system_theme(self):
        self._apply("dark" if self._is_system_dark() else "light")

    def _on_scheme_changed(self, _):
        if self._mode == "system":
            self._apply_system_theme()

    def _is_system_dark(self) -> bool:
        try:
            from PySide6.QtCore import Qt
            scheme = QApplication.styleHints().colorScheme()
            return scheme == Qt.ColorScheme.Dark
        except (AttributeError, ImportError):
            pass
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return val == 0
        except Exception:
            return False

    def _apply(self, theme):
        self._current = theme
        self._colors = ThemeColors(theme == "dark")
        qss_path = _resource_path(f"app/styles/{theme}.qss")
        app = QApplication.instance()
        if app is None:
            return
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
            # Resolve relative asset URLs to absolute paths
            asset_dir = _resource_path("assets").replace("\\", "/")
            qss = qss.replace("url(assets/", f"url({asset_dir}/")
            app.setStyleSheet(qss)
        except FileNotFoundError:
            app.setStyleSheet("")
        self.theme_changed.emit(theme)

    def accent_color(self): return self.BRAND
    def text_color(self): return self._colors.primary_text
    def bg_color(self): return self._colors.bg
    def card_bg_color(self): return self._colors.card_bg
    def border_color(self): return self._colors.border
