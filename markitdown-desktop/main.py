# SPDX-License-Identifier: MIT

import sys
import os

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QMainWindow,
)

from app.__about__ import __version__, __app_name__
from app.settings import AppSettings
from app.theme import ThemeManager
from app.history import HistoryManager
from app.main_window import MainWindow
from app.float_window import FloatWindow


def _smoke_convert(file_path: str, result_path: str | None = None) -> int:
    """Headless conversion entry point used by clean-machine package tests."""
    try:
        from markitdown import MarkItDown

        result = MarkItDown().convert(file_path)
        output = result.markdown or "# MarkItDown conversion completed"
        if result_path:
            with open(result_path, "w", encoding="utf-8") as stream:
                stream.write("ok\n" + output)
        else:
            print(output)
        return 0
    except Exception as exc:
        if result_path:
            with open(result_path, "w", encoding="utf-8") as stream:
                stream.write("error\n" + str(exc))
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    if "--smoke-convert" in sys.argv:
        index = sys.argv.index("--smoke-convert")
        if index + 1 >= len(sys.argv):
            raise SystemExit(2)
        result_path = None
        if "--smoke-output" in sys.argv:
            output_index = sys.argv.index("--smoke-output")
            if output_index + 1 < len(sys.argv):
                result_path = sys.argv[output_index + 1]
        raise SystemExit(_smoke_convert(sys.argv[index + 1], result_path))
    app = QApplication(sys.argv)
    app.setApplicationName("MarkConvert Desk")
    app.setOrganizationName(__app_name__)
    app.setQuitOnLastWindowClosed(False)

    icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    icon = QIcon()
    icon.addFile(os.path.join(icon_dir, "icon_16.png"), QSize(16, 16))
    icon.addFile(os.path.join(icon_dir, "icon_32.png"), QSize(32, 32))
    icon.addFile(os.path.join(icon_dir, "icon_128.png"), QSize(128, 128))

    # ── 核心模块 ──
    settings = AppSettings()
    theme_mgr = ThemeManager()
    history_mgr = HistoryManager(max_entries=settings.max_history)

    # ── 窗口 ──
    main_win = MainWindow(settings, theme_mgr, history_mgr)
    app.aboutToQuit.connect(main_win._jobs.store.cleanup)
    main_win.setWindowIcon(icon)

    float_win = FloatWindow(settings, theme_mgr)
    float_win.setWindowIcon(icon)
    main_win.set_float_window(float_win)

    # ── 信号连接 ──
    float_win.file_dropped.connect(lambda p: main_win._on_files_dropped([p]))
    float_win.show_main_requested.connect(main_win.show)
    float_win.show_main_requested.connect(main_win.raise_)
    float_win.show_main_requested.connect(main_win.activateWindow)
    float_win.show_settings_requested.connect(main_win._open_settings)

    # 历史更新时同步更新悬浮窗
    orig_refresh = main_win._refresh_history

    def _refresh_and_sync():
        orig_refresh()
        float_win.set_history_entries(history_mgr.entries)

    main_win._refresh_history = _refresh_and_sync
    float_win.set_history_entries(history_mgr.entries)

    # ── 初始化主题 ──
    theme_mgr.set_mode(settings.theme_mode)

    # ── 系统托盘 ──
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("MarkItDownDesk")

    tray_menu = QMenu()
    a_show = QAction("显示主窗口", tray_menu)
    a_show.triggered.connect(main_win.show)
    a_show.triggered.connect(main_win.raise_)
    a_show.triggered.connect(main_win.activateWindow)
    tray_menu.addAction(a_show)

    a_float = QAction("显示悬浮窗", tray_menu)
    a_float.triggered.connect(float_win.show)
    a_float.triggered.connect(float_win.raise_)
    tray_menu.addAction(a_float)

    tray_menu.addSeparator()

    a_theme = QAction("切换主题", tray_menu)
    a_theme.triggered.connect(lambda: theme_mgr.toggle())
    tray_menu.addAction(a_theme)

    a_quit = QAction("退出", tray_menu)
    a_quit.triggered.connect(app.quit)
    tray_menu.addAction(a_quit)

    tray.setContextMenu(tray_menu)
    tray.show()

    # ── 显示窗口 ──
    main_win.show()
    if settings.show_float_window:
        float_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
