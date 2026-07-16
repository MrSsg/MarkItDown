# SPDX-License-Identifier: MIT
"""Dialogs: SettingsDialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QDialogButtonBox, QRadioButton,
    QCheckBox, QSlider, QSpinBox, QFormLayout, QMessageBox)
from app.settings import AppSettings
from app.theme import ThemeManager


class SettingsDialog(QDialog):
    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._theme = theme_mgr
        self.setWindowTitle("偏好设置")
        self.setMinimumWidth(460)
        self._build_ui()
        self._load_values()

    def _check_and_show_update(self):
        from app.__about__ import __version__ as _av, __app_name__ as _an
        from app.updater import get_local_kernel_version as _kv, check_latest_release as _cr
        _k = _kv()
        _r = _cr()
        _m = f"<h3>{_an} v{_av}</h3>"
        _m += f"<p>内核: <b>markitdown v{_k}</b></p>"
        if _r:
            if _r.version > _k:
                _m += f'<p style="color:#407BFF">📦 新内核 <b>v{_r.version}</b> 可用</p>'
                _m += f'<p><a href="{_r.html_url}">查看发布页</a></p>'
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
        from app.updater import get_local_kernel_version as _kv
        _k = _kv()
        about_layout.addWidget(QLabel(f"<b>{_an}</b> v{_av}"))
        about_layout.addWidget(QLabel(f"内核: markitdown v{_k}"))
        _cb = QPushButton("检查更新")
        _cb.clicked.connect(self._check_and_show_update)
        about_layout.addWidget(_cb)
        l.addWidget(about_group)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save_values); btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        l.addWidget(btns)

    def _load_values(self):
        mode = self._settings.theme_mode or "system"
        if mode == "system": self._sys_rb.setChecked(True)
        elif mode == "dark": self._dark_rb.setChecked(True)
        else: self._light_rb.setChecked(True)
        self._ask_cb.setChecked(self._settings.ask_save_each_time)
        if not self._settings.ask_save_each_time:
            self._path_lbl.setText(self._settings.default_save_path or "（未设置）")
        self._max_spin.setValue(self._settings.max_history)

    def _save_values(self):
        if self._sys_rb.isChecked(): self._settings.theme_mode = "system"
        elif self._dark_rb.isChecked(): self._settings.theme_mode = "dark"
        else: self._settings.theme_mode = "light"
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


