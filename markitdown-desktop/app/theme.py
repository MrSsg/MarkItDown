# SPDX-License-Identifier: MIT

import os, sys
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

def _resource_path(relative: str) -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

class ThemePalette:
    """Holds the full color palette for one theme (light or dark)."""
    def __init__(self, is_dark: bool):
        if is_dark:
            self.bg = "#12141A"
            self.card_bg = "#1C1F28"
            self.card_hover = "#272B36"
            self.primary_text = "#F5F7FA"
            self.body_text = "#D5D9E2"
            self.secondary_text = "#AAB2C0"
            self.border = "#303643"
            self.accent_border = "#407BFF50"
            self.topbar_bg = "#1C1F28"
            self.brand_strong = "#78A8FF"
            self.brand_text = "#A7C7FF"
            self.brand_on = "#10233F"
            self.focus = "#9CC0FF"
            self.success_text = "#56D364"
            self.warning_text = "#FDB022"
            self.error_text = "#FF8A8A"
            self.success_bg = "#123A24"
            self.warning_bg = "#3D2B13"
            self.error_bg = "#421F24"
        else:
            self.bg = "#F7F8FC"
            self.card_bg = "#FFFFFF"
            self.card_hover = "#F2F5FF"
            self.primary_text = "#1D2129"
            self.body_text = "#344054"
            self.secondary_text = "#667085"
            self.border = "#E5E6EB"
            self.accent_border = "#407BFF40"
            self.topbar_bg = "#FFFFFF"
            self.brand_strong = "#245FD6"
            self.brand_text = "#1F5BC9"
            self.brand_on = "#FFFFFF"
            self.focus = "#245FD6"
            self.success_text = "#087F23"
            self.warning_text = "#B54708"
            self.error_text = "#D92D20"
            self.success_bg = "#ECFDF3"
            self.warning_bg = "#FFFAEB"
            self.error_bg = "#FEF3F2"
        self.brand = "#407BFF"
        self.success = self.success_text
        self.warning = self.warning_text
        self.error = self.error_text

class ThemeManager(QObject):
    theme_changed = Signal(str)

    BRAND = "#407BFF"
    SUCCESS = "#087F23"
    WARNING = "#B54708"
    ERROR = "#D92D20"
    DISABLED = "#667085"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "system"
        self._current = "light"
        self._colors = ThemePalette(False)
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
        self._colors = ThemePalette(theme == "dark")
        qss_path = _resource_path(f"app/styles/{theme}.qss")
        app = QApplication.instance()
        if app is None or not hasattr(app, "setStyleSheet"):
            return
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
            tokens = {
                "@BG@": self._colors.bg, "@CARD@": self._colors.card_bg,
                "@HOVER@": self._colors.card_hover, "@TEXT@": self._colors.primary_text,
                "@BODY@": self._colors.body_text, "@MUTED@": self._colors.secondary_text,
                "@BORDER@": self._colors.border, "@BRAND@": self._colors.brand,
                "@BRAND_STRONG@": self._colors.brand_strong,
                "@BRAND_TEXT@": self._colors.brand_text,
                "@BRAND_ON@": self._colors.brand_on,
                "@FOCUS@": self._colors.focus,
                "@SUCCESS@": self._colors.success_text,
                "@WARNING@": self._colors.warning_text,
                "@ERROR@": self._colors.error_text,
                "@SUCCESS_BG@": self._colors.success_bg,
                "@WARNING_BG@": self._colors.warning_bg,
                "@ERROR_BG@": self._colors.error_bg,
            }
            for key, value in tokens.items():
                qss = qss.replace(key, value)
            app.setStyleSheet(qss)
        except FileNotFoundError:
            app.setStyleSheet("")
        self.theme_changed.emit(theme)

    def accent_color(self): return self.BRAND
    def text_color(self): return self._colors.primary_text
    def bg_color(self): return self._colors.bg
    def card_bg_color(self): return self._colors.card_bg
    def border_color(self): return self._colors.border
