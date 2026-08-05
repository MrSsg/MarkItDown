# SPDX-License-Identifier: MIT
"""Dialogs: SettingsDialog."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QDialogButtonBox, QRadioButton,
    QCheckBox, QSpinBox, QMessageBox, QProgressBar)

from .ocr import OcrComponentError, OcrComponentManager


class _OcrInstallThread(QThread):
    progress = Signal(int)
    complete = Signal(object)
    failed = Signal(object)

    def __init__(self, manager):
        super().__init__()
        self._manager = manager

    def run(self):
        try:
            info = self._manager.install_from_manifest_url(
                progress=lambda value: self.progress.emit(round(value * 100))
            )
            self.complete.emit(info)
        except OcrComponentError as exc:
            self.failed.emit({"code": exc.code, "message": str(exc)})


class OcrInstallDialog(QDialog):
    """Install or import the optional, locally executed OCR component."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._thread = None
        self.setWindowTitle("安装离线 OCR")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        self._status = QLabel("OCR 会在本机处理图片和扫描 PDF，不上传文件。")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        buttons = QHBoxLayout()
        self._download = QPushButton("下载并安装")
        self._download.clicked.connect(self._download_component)
        self._import = QPushButton("导入离线组件")
        self._import.clicked.connect(self._import_component)
        buttons.addWidget(self._download)
        buttons.addWidget(self._import)
        layout.addLayout(buttons)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _download_component(self):
        self._download.setEnabled(False)
        self._import.setEnabled(False)
        self._status.setText("正在下载 OCR 组件…")
        self._thread = _OcrInstallThread(self._manager)
        self._thread.progress.connect(self._progress.setValue)
        self._thread.complete.connect(self._installed)
        self._thread.failed.connect(self._failed)
        self._thread.start()

    def _import_component(self):
        archive, _ = QFileDialog.getOpenFileName(self, "选择 OCR 组件 ZIP", "", "ZIP (*.zip)")
        if not archive:
            return
        manifest, _ = QFileDialog.getOpenFileName(self, "选择 OCR 组件清单", "", "JSON (*.json)")
        if not manifest:
            return
        try:
            self._installed(self._manager.install_offline_archive(archive, manifest))
        except OcrComponentError as exc:
            self._failed({"code": exc.code, "message": str(exc)})

    def _installed(self, info):
        self._progress.setValue(100)
        self._status.setText(f"OCR 组件已安装：v{info.version}")
        self._download.setEnabled(True)
        self._import.setEnabled(True)

    def _failed(self, error):
        payload = error if isinstance(error, dict) else {"code": "OCR_COMPONENT_ERROR", "message": str(error)}
        self._status.setText(f"安装失败 [{payload['code']}]：{payload['message']}")
        self._download.setEnabled(True)
        self._import.setEnabled(True)


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

        limits_group = QGroupBox("资源保护")
        limits_layout = QVBoxLayout(limits_group)
        self._max_file_spin = QSpinBox(); self._max_file_spin.setRange(200, 2048); self._max_file_spin.setSuffix(" MiB / 文件")
        self._max_batch_spin = QSpinBox(); self._max_batch_spin.setRange(1, 1000); self._max_batch_spin.setSuffix(" 项 / 批次")
        self._max_pdf_spin = QSpinBox(); self._max_pdf_spin.setRange(500, 5000); self._max_pdf_spin.setSuffix(" 页 / PDF")
        self._max_zip_spin = QSpinBox(); self._max_zip_spin.setRange(1024, 10240); self._max_zip_spin.setSuffix(" MiB / ZIP 展开")
        for control in (self._max_file_spin, self._max_batch_spin, self._max_pdf_spin, self._max_zip_spin):
            limits_layout.addWidget(control)
        l.addWidget(limits_group)

        # About section
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        from app.__about__ import __version__ as _av, __app_name__ as _an
        self._about_app_lbl = QLabel(f"<b>{_an}</b> v{_av}")
        self._about_kernel_lbl = QLabel("转换内核随完整桌面发行版更新")
        ocr_info = OcrComponentManager().status()
        self._about_ocr_lbl = QLabel(
            f"离线 OCR：已安装 v{ocr_info.version}" if ocr_info.installed else "离线 OCR：未安装"
        )
        self._about_links_lbl = QLabel(
            '<a href="https://github.com/MrSsg/MarkItDown/releases">发行版</a>  ·  '
            '<a href="https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE">PaddleOCR Apache-2.0</a>'
        )
        self._about_links_lbl.setOpenExternalLinks(True)
        about_layout.addWidget(self._about_app_lbl)
        about_layout.addWidget(self._about_kernel_lbl)
        about_layout.addWidget(self._about_ocr_lbl)
        about_layout.addWidget(self._about_links_lbl)
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
        self._max_file_spin.setValue(self._settings.max_file_mib)
        self._max_batch_spin.setValue(self._settings.max_batch_items)
        self._max_pdf_spin.setValue(self._settings.max_pdf_pages)
        self._max_zip_spin.setValue(self._settings.max_zip_mib)

    def _save_values(self):
        if self._sys_rb.isChecked(): self._settings.theme_mode = "system"
        elif self._dark_rb.isChecked(): self._settings.theme_mode = "dark"
        else: self._settings.theme_mode = "light"
        self._settings.show_float_window = self._float_cb.isChecked()
        self._settings.close_to_tray = self._tray_rb.isChecked()
        self._settings.ask_save_each_time = self._ask_cb.isChecked()
        self._settings.max_history = self._max_spin.value()
        self._settings.max_file_mib = self._max_file_spin.value()
        self._settings.max_batch_items = self._max_batch_spin.value()
        self._settings.max_pdf_pages = self._max_pdf_spin.value()
        self._settings.max_zip_mib = self._max_zip_spin.value()
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
