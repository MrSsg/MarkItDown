# SPDX-License-Identifier: MIT
"""Dialogs: SettingsDialog."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QDialogButtonBox, QRadioButton,
    QCheckBox, QSpinBox, QMessageBox)


class SettingsDialog(QDialog):
    def __init__(self, settings, theme_mgr, float_win=None, parent=None):
        super().__init__(parent)
        self._float_win = float_win
        self._settings = settings
        self._theme = theme_mgr
        self.setWindowTitle("偏好设置")
        self.setMinimumWidth(460)
        self._build_ui()
        self._load_values()
        QTimer.singleShot(0, self._populate_about_info)

    def _check_and_show_update(self):
        from app.__about__ import __version__ as _av, __app_name__ as _an
        from app.updater import get_local_kernel_version as _kv, check_latest_release as _cr
        _k = _kv()
        _r = _cr()
        _m = f"<h3>{_an} v{_av}</h3>"
        _m += f"<p>内核: <b>markitdown v{_k}</b></p>"
        if _r:
            if _r.version > _k:
                _m += '<p style="color:#407BFF">📦 新内核 <b>v' + _r.version + '</b> 可用</p>'
                _m += '<p><a href="' + _r.html_url + '">查看发布页</a></p>'
            else:
                _m += '<p style="color:#4CAF50">✅ 内核已是最新</p>'
        else:
            _m += '<p style="color:#888">未能检查更新（网络不可达）</p>'
        _m += "<hr><p style='color:#888'>基于 Microsoft MarkItDown 的桌面转换工具</p>"
        QMessageBox.about(self, f"关于 {_an}", _m)

    def _build_ui(self):
        l = QVBoxLayout(self)
        l.setSpacing(16)
        g1 = QGroupBox("保存路径")
        g1l = QVBoxLayout(g1)
        self._path_lbl = QLabel(self._settings.default_save_path or "（未设置）")
        self._path_lbl.setWordWrap(True)
        br = QHBoxLayout()
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_path)
        self._ask_cb = QCheckBox("每次询问")
        self._ask_cb.toggled.connect(lambda c: browse_btn.setEnabled(not c))
        br.addWidget(browse_btn); br.addWidget(self._ask_cb); br.addStretch()
        g1l.addWidget(self._path_lbl); g1l.addLayout(br)
        l.addWidget(g1)

        g2 = QGroupBox("主题")
        g2l = QVBoxLayout(g2)
        self._sys_rb = QRadioButton("跟随系统")
        self._dark_rb = QRadioButton("深色")
        self._light_rb = QRadioButton("浅色")
        g2l.addWidget(self._sys_rb); g2l.addWidget(self._dark_rb); g2l.addWidget(self._light_rb)
        l.addWidget(g2)
        self._sys_rb.toggled.connect(self._on_theme_toggled)
        self._dark_rb.toggled.connect(self._on_theme_toggled)
        self._light_rb.toggled.connect(self._on_theme_toggled)

        # 悬浮窗开关
        g_float = QGroupBox("悬浮窗")
        g_float_l = QVBoxLayout(g_float)
        self._float_cb = QCheckBox("开启悬浮窗")
        self._float_cb.toggled.connect(self._on_float_toggled)
        g_float_l.addWidget(self._float_cb)
        l.addWidget(g_float)

        # 关闭行为
        g_exit = QGroupBox("关闭主窗口时")
        g_exit_l = QVBoxLayout(g_exit)
        self._tray_rb = QRadioButton("最小化到系统托盘")
        self._quit_rb = QRadioButton("完全退出应用")
        g_exit_l.addWidget(self._tray_rb); g_exit_l.addWidget(self._quit_rb)
        l.addWidget(g_exit)

        g3 = QGroupBox("历史记录")
        g3l = QVBoxLayout(g3)
        hr = QHBoxLayout()
        hr.addWidget(QLabel("最大条数："))
        self._max_spin = QSpinBox(); self._max_spin.setRange(10, 200)
        hr.addWidget(self._max_spin); hr.addStretch()
        g3l.addLayout(hr)
        clear_btn = QPushButton("清空历史")
        clear_btn.clicked.connect(self._clear_history)
        g3l.addWidget(clear_btn)
        l.addWidget(g3)

        # About section
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        from app.__about__ import __version__ as _av, __app_name__ as _an
        self._about_app_lbl = QLabel(f"<b>{_an}</b> v{_av}")
        self._about_kernel_lbl = QLabel("内核: 正在读取...")
        about_layout.addWidget(self._about_app_lbl)
        about_layout.addWidget(self._about_kernel_lbl)
        _cb = QPushButton("检查更新")
        _cb.clicked.connect(self._check_and_show_update)
        about_layout.addWidget(_cb)
        l.addWidget(about_group)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save_values); btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        l.addWidget(btns)

    def _on_float_toggled(self, checked):
        if self._float_win:
            if checked:
                self._float_win.show()
                self._float_win.raise_()
            else:
                self._float_win.hide()

    def _on_theme_toggled(self, checked):
        if not checked:
            return
        if self._sys_rb.isChecked():
            self._theme.set_mode("system")
        elif self._dark_rb.isChecked():
            self._theme.set_mode("dark")
        else:
            self._theme.set_mode("light")

    def _load_values(self):
        mode = self._settings.theme_mode or "system"
        if mode == "system": self._sys_rb.setChecked(True)
        elif mode == "dark": self._dark_rb.setChecked(True)
        else: self._light_rb.setChecked(True)
        self._float_cb.setChecked(self._settings.show_float_window)
        if self._settings.close_to_tray:
            self._tray_rb.setChecked(True)
        else:
            self._quit_rb.setChecked(True)
        self._ask_cb.setChecked(self._settings.ask_save_each_time)
        if not self._settings.ask_save_each_time:
            self._path_lbl.setText(self._settings.default_save_path or "（未设置）")
        self._max_spin.setValue(self._settings.max_history)

    def _populate_about_info(self):
        from app.updater import get_local_kernel_version as _kv

        self._about_kernel_lbl.setText(f"内核: markitdown v{_kv()}")

    def _save_values(self):
        if self._sys_rb.isChecked(): self._settings.theme_mode = "system"
        elif self._dark_rb.isChecked(): self._settings.theme_mode = "dark"
        else: self._settings.theme_mode = "light"
        self._settings.show_float_window = self._float_cb.isChecked()
        self._settings.close_to_tray = self._tray_rb.isChecked()
        self._settings.ask_save_each_time = self._ask_cb.isChecked()
        self._settings.max_history = self._max_spin.value()
        self._settings.sync()
        self._theme.set_mode(self._settings.theme_mode)

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择默认保存路径")
        if path:
            self._settings.default_save_path = path
            self._path_lbl.setText(path)
            self._settings.sync()

    def _clear_history(self):
        parent = self.parent()
        if hasattr(parent, "history_mgr"):
            parent.history_mgr.clear()
