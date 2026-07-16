# SPDX-License-Identifier: MIT

from PySide6.QtCore import QSettings, QPoint, QByteArray


class AppSettings:
    """应用设置管理，基于 QSettings 持久化。"""

    def __init__(self) -> None:
        self._settings = QSettings("MarkItDownDesk", "MarkItDownDesk")

    # ── 保存路径 ──────────────────────────────────────────

    @property
    def default_save_path(self) -> str:
        return self._settings.value("save/default_path", "", type=str)

    @default_save_path.setter
    def default_save_path(self, path: str) -> None:
        self._settings.setValue("save/default_path", path)

    @property
    def ask_save_each_time(self) -> bool:
        return self._settings.value("save/ask_each_time", True, type=bool)

    @ask_save_each_time.setter
    def ask_save_each_time(self, val: bool) -> None:
        self._settings.setValue("save/ask_each_time", val)

    # ── 主题 ──────────────────────────────────────────────

    @property
    def theme_mode(self) -> str:
        return self._settings.value("theme/mode", "system", type=str)

    @theme_mode.setter
    def theme_mode(self, mode: str) -> None:
        self._settings.setValue("theme/mode", mode)

    # ── 悬浮窗 ────────────────────────────────────────────

    @property
    def float_position(self) -> QPoint | None:
        v = self._settings.value("float/position")
        return v if isinstance(v, QPoint) else None

    @float_position.setter
    def float_position(self, pos: QPoint) -> None:
        self._settings.setValue("float/position", pos)

    @property
    def float_edge(self) -> str | None:
        return self._settings.value("float/edge", None, type=str)  # type: ignore[return-value]

    @float_edge.setter
    def float_edge(self, edge: str | None) -> None:
        if edge is None:
            self._settings.remove("float/edge")
        else:
            self._settings.setValue("float/edge", edge)

    # ── 主窗口 ────────────────────────────────────────────

    @property
    def window_geometry(self) -> QByteArray | None:
        v = self._settings.value("window/geometry")
        return v if isinstance(v, QByteArray) else None

    @window_geometry.setter
    def window_geometry(self, geo: QByteArray) -> None:
        self._settings.setValue("window/geometry", geo)

    @property
    def window_splitter_outer(self) -> QByteArray | None:
        v = self._settings.value("window/splitter_outer")
        return v if isinstance(v, QByteArray) else None

    @window_splitter_outer.setter
    def window_splitter_outer(self, state: QByteArray) -> None:
        self._settings.setValue("window/splitter_outer", state)

    @property
    def window_splitter_inner(self) -> QByteArray | None:
        v = self._settings.value("window/splitter_inner")
        return v if isinstance(v, QByteArray) else None

    @window_splitter_inner.setter
    def window_splitter_inner(self, state: QByteArray) -> None:
        self._settings.setValue("window/splitter_inner", state)

    # ── 折叠延迟 ──────────────────────────────────────────

    @property
    def collapse_delay(self) -> int:
        return self._settings.value("float/collapse_delay", 800, type=int)

    @collapse_delay.setter
    def collapse_delay(self, ms: int) -> None:
        self._settings.setValue("float/collapse_delay", ms)

    # ── 透明度 ────────────────────────────────────────────

    @property
    def float_opacity(self) -> float:
        return self._settings.value("float/opacity", 0.92, type=float)

    @float_opacity.setter
    def float_opacity(self, val: float) -> None:
        self._settings.setValue("float/opacity", val)

    # ── 历史条数 ──────────────────────────────────────────

    @property
    def max_history(self) -> int:
        return self._settings.value("history/max", 50, type=int)

    @max_history.setter
    def max_history(self, val: int) -> None:
        self._settings.setValue("history/max", val)

    # ── 写入磁盘 ──────────────────────────────────────────

    def sync(self) -> None:
        self._settings.sync()
