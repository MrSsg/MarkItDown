# SPDX-License-Identifier: MIT
"""Install and preference dialogs for the desktop workspace."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .ocr import OcrComponentError, OcrComponentManager


class _OcrInstallThread(QThread):
    progress = Signal(int)
    complete = Signal(object)
    failed = Signal(object)

    def __init__(self, manager, archive: str | None = None, manifest: str | None = None, cancel_event=None):
        super().__init__()
        self._manager = manager
        self._archive = archive
        self._manifest = manifest
        self._cancel_event = cancel_event or threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()
        self.requestInterruption()

    def run(self):
        try:
            if self._archive and self._manifest:
                info = self._manager.install_offline_archive(self._archive, self._manifest)
            else:
                info = self._manager.install_from_manifest_url(
                    progress=lambda value: self.progress.emit(round(value * 100)),
                    cancel_event=self._cancel_event,
                )
            self.complete.emit(info)
        except OcrComponentError as exc:
            self.failed.emit({"code": exc.code, "message": str(exc)})
        except Exception as exc:
            self.failed.emit({"code": "OCR_COMPONENT_ERROR", "message": str(exc)})


class OcrInstallDialog(QDialog):
    """Install or import the optional, locally executed OCR component."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._thread: _OcrInstallThread | None = None
        self._cancel_event = threading.Event()
        self._install_active = False
        self.setWindowTitle("安装离线 OCR")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        self._status = QLabel("OCR 会在本机处理图片和扫描 PDF，不上传文件。")
        self._status.setObjectName("mutedText")
        self._status.setWordWrap(True)
        self._status.setAccessibleName("OCR 安装状态")
        layout.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setAccessibleName("OCR 安装进度")
        layout.addWidget(self._progress)
        self._phase = QLabel("支持自动下载签名组件或导入离线 ZIP 与清单。")
        self._phase.setObjectName("mutedText")
        self._phase.setWordWrap(True)
        layout.addWidget(self._phase)

        buttons = QHBoxLayout()
        self._download = QPushButton("下载并安装")
        self._download.setAccessibleName("下载并安装离线 OCR")
        self._download.clicked.connect(self._download_component)
        self._import = QPushButton("导入离线组件")
        self._import.setAccessibleName("导入离线 OCR 组件")
        self._import.clicked.connect(self._import_component)
        buttons.addWidget(self._download)
        buttons.addWidget(self._import)
        layout.addLayout(buttons)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._close_button = self._buttons.button(QDialogButtonBox.StandardButton.Close)
        self._close_button.setText("关闭")
        self._close_button.clicked.connect(self.reject)
        self._cancel_button = self._buttons.addButton("取消安装", QDialogButtonBox.ButtonRole.RejectRole)
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._cancel_install)
        layout.addWidget(self._buttons)

    def _set_busy(self, busy: bool) -> None:
        self._install_active = busy
        self._download.setEnabled(not busy)
        self._import.setEnabled(not busy)
        self._close_button.setEnabled(not busy)
        self._cancel_button.setEnabled(busy)

    def _start_thread(self, archive: str | None = None, manifest: str | None = None) -> None:
        self._cancel_event.clear()
        self._progress.setValue(0)
        self._set_busy(True)
        self._thread = _OcrInstallThread(self._manager, archive, manifest, self._cancel_event)
        self._thread.progress.connect(self._progress.setValue)
        self._thread.complete.connect(self._installed)
        self._thread.failed.connect(self._failed)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    def _download_component(self):
        current = self._manager.status()
        if current.installed:
            self._status.setText(f"已安装 v{current.version}，正在检查最新版本…")
            self._phase.setText("若已是最新版，将直接复用本地组件，不会重复下载。")
        else:
            self._status.setText("正在下载并校验 OCR 组件…")
            self._phase.setText("下载完成后会验证签名、SHA-256 和引擎健康状态。")
        self._start_thread()

    def _import_component(self):
        archive, _ = QFileDialog.getOpenFileName(self, "选择 OCR 组件 ZIP", "", "ZIP (*.zip)")
        if not archive:
            return
        manifest, _ = QFileDialog.getOpenFileName(self, "选择 OCR 组件清单", "", "JSON (*.json)")
        if not manifest:
            return
        self._status.setText("正在校验并导入离线 OCR 组件…")
        self._phase.setText("离线导入不会访问网络，完成后会运行本地健康检查。")
        self._start_thread(archive, manifest)

    def _cancel_install(self):
        if self._thread and self._thread.isRunning():
            self._thread.request_cancel()
            self._cancel_button.setEnabled(False)
            self._status.setText("正在取消安装，等待当前步骤安全结束…")
            self._phase.setText("不会强制终止正在写入的组件文件。")

    def _installed(self, info):
        self._progress.setValue(100)
        self._status.setText(info.message or f"OCR 组件已安装：v{info.version}")
        self._phase.setText("组件已通过健康检查，可在转换选项中启用。")

    def _failed(self, error):
        payload = error if isinstance(error, dict) else {"code": "OCR_COMPONENT_ERROR", "message": str(error)}
        self._status.setText(f"安装失败 [{payload['code']}]：{payload['message']}")
        self._phase.setText("可以修正网络/清单后重试，或导入匹配版本的离线组件。")

    def _thread_finished(self):
        thread = self._thread
        self._set_busy(False)
        self._thread = None
        if thread:
            thread.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread and self._thread.isRunning():
            self._cancel_install()
            event.ignore()
            return
        event.accept()


class SettingsDialog(QDialog):
    def __init__(self, settings, theme_mgr, float_win=None, parent=None):
        super().__init__(parent)
        self._float_win = float_win
        self._settings = settings
        self._theme = theme_mgr
        self._loading = True
        self._committed = False
        self._draft_save_path = settings.default_save_path
        self._snapshot = {
            "theme_mode": theme_mgr.mode,
            "float_visible": bool(float_win and float_win.isVisible()),
            "reduce_motion": settings.reduce_motion,
        }
        self.setWindowTitle("偏好设置")
        self.setMinimumSize(500, 560)
        self._build_ui()
        self._load_values()
        self._loading = False

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(14)

        g1 = QGroupBox("保存路径")
        g1l = QVBoxLayout(g1)
        self._path_lbl = QLabel()
        self._path_lbl.setObjectName("mutedText")
        self._path_lbl.setWordWrap(True)
        br = QHBoxLayout()
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_path)
        self._ask_cb = QCheckBox("每次导出时询问位置")
        self._ask_cb.toggled.connect(lambda checked: browse_btn.setEnabled(not checked))
        br.addWidget(browse_btn)
        br.addWidget(self._ask_cb)
        br.addStretch()
        g1l.addWidget(self._path_lbl)
        g1l.addLayout(br)
        content_layout.addWidget(g1)

        g2 = QGroupBox("主题")
        g2l = QVBoxLayout(g2)
        self._sys_rb = QRadioButton("跟随系统")
        self._dark_rb = QRadioButton("深色")
        self._light_rb = QRadioButton("浅色")
        for control in (self._sys_rb, self._dark_rb, self._light_rb):
            g2l.addWidget(control)
            control.toggled.connect(self._on_theme_toggled)
        content_layout.addWidget(g2)

        g_float = QGroupBox("快捷悬浮窗")
        g_float_l = QVBoxLayout(g_float)
        self._float_cb = QCheckBox("显示快捷导入与任务摘要")
        self._float_cb.toggled.connect(self._on_float_toggled)
        g_float_l.addWidget(self._float_cb)
        content_layout.addWidget(g_float)

        g_access = QGroupBox("辅助功能")
        access_layout = QVBoxLayout(g_access)
        self._motion_cb = QCheckBox("减少主题与悬浮窗动效")
        self._motion_cb.setAccessibleName("减少界面动效")
        self._motion_cb.toggled.connect(self._on_motion_toggled)
        access_layout.addWidget(self._motion_cb)
        access_hint = QLabel("启用后状态切换会即时完成，适合对动画敏感的用户。")
        access_hint.setObjectName("mutedText")
        access_hint.setWordWrap(True)
        access_layout.addWidget(access_hint)
        content_layout.addWidget(g_access)

        g_exit = QGroupBox("关闭主窗口时")
        g_exit_l = QVBoxLayout(g_exit)
        self._tray_rb = QRadioButton("最小化到系统托盘")
        self._quit_rb = QRadioButton("完全退出应用")
        g_exit_l.addWidget(self._tray_rb)
        g_exit_l.addWidget(self._quit_rb)
        content_layout.addWidget(g_exit)

        g3 = QGroupBox("历史记录")
        g3l = QVBoxLayout(g3)
        history_form = QFormLayout()
        self._max_spin = QSpinBox()
        self._max_spin.setRange(10, 200)
        self._max_spin.setSuffix(" 项")
        self._max_spin.setAccessibleName("历史记录最大条数")
        history_form.addRow("最多保留：", self._max_spin)
        g3l.addLayout(history_form)
        clear_btn = QPushButton("清空历史…")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._clear_history)
        g3l.addWidget(clear_btn)
        content_layout.addWidget(g3)

        limits_group = QGroupBox("资源保护")
        limits_layout = QVBoxLayout(limits_group)
        limits_hint = QLabel("限制在入队前生效，ZIP 安全检查始终开启。")
        limits_hint.setObjectName("mutedText")
        limits_hint.setWordWrap(True)
        limits_layout.addWidget(limits_hint)
        limits_form = QFormLayout()
        self._max_file_spin = QSpinBox()
        self._max_file_spin.setRange(200, 2048)
        self._max_file_spin.setSuffix(" MiB")
        self._max_batch_spin = QSpinBox()
        self._max_batch_spin.setRange(1, 1000)
        self._max_batch_spin.setSuffix(" 项")
        self._max_pdf_spin = QSpinBox()
        self._max_pdf_spin.setRange(500, 5000)
        self._max_pdf_spin.setSuffix(" 页")
        self._max_zip_spin = QSpinBox()
        self._max_zip_spin.setRange(1024, 10240)
        self._max_zip_spin.setSuffix(" MiB")
        controls = (
            ("单文件上限：", self._max_file_spin, "单个输入文件"),
            ("批次上限：", self._max_batch_spin, "单批任务数量"),
            ("PDF 页数上限：", self._max_pdf_spin, "单个 PDF 页数"),
            ("ZIP 展开上限：", self._max_zip_spin, "ZIP 解压后的总大小"),
        )
        for label, control, accessible in controls:
            control.setAccessibleName(accessible)
            limits_form.addRow(label, control)
        limits_layout.addLayout(limits_form)
        content_layout.addWidget(limits_group)

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
        for label in (self._about_app_lbl, self._about_kernel_lbl, self._about_ocr_lbl, self._about_links_lbl):
            about_layout.addWidget(label)
        content_layout.addWidget(about_group)
        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save_values)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_float_toggled(self, checked):
        if self._loading or not self._float_win:
            return
        if checked:
            self._float_win.show()
            self._float_win.raise_()
        else:
            self._float_win.hide()

    def _on_theme_toggled(self, checked):
        if self._loading or not checked:
            return
        if self._sys_rb.isChecked():
            self._theme.set_mode("system")
        elif self._dark_rb.isChecked():
            self._theme.set_mode("dark")
        else:
            self._theme.set_mode("light")

    def _on_motion_toggled(self, reduced: bool) -> None:
        if self._loading:
            return
        parent = self.parent()
        if hasattr(parent, "_theme_btn"):
            parent._theme_btn.set_reduced_motion(reduced)
        if self._float_win:
            self._float_win.set_reduced_motion(reduced)

    def _load_values(self):
        mode = self._settings.theme_mode or "system"
        buttons = {"system": self._sys_rb, "dark": self._dark_rb, "light": self._light_rb}
        buttons.get(mode, self._sys_rb).setChecked(True)
        self._float_cb.setChecked(self._settings.show_float_window)
        self._motion_cb.setChecked(self._settings.reduce_motion)
        self._tray_rb.setChecked(self._settings.close_to_tray)
        self._quit_rb.setChecked(not self._settings.close_to_tray)
        self._ask_cb.setChecked(self._settings.ask_save_each_time)
        self._path_lbl.setText(self._settings.default_save_path or "（未设置）")
        self._max_spin.setValue(self._settings.max_history)
        self._max_file_spin.setValue(self._settings.max_file_mib)
        self._max_batch_spin.setValue(self._settings.max_batch_items)
        self._max_pdf_spin.setValue(self._settings.max_pdf_pages)
        self._max_zip_spin.setValue(self._settings.max_zip_mib)

    def _save_values(self):
        if self._sys_rb.isChecked():
            mode = "system"
        elif self._dark_rb.isChecked():
            mode = "dark"
        else:
            mode = "light"
        self._settings.theme_mode = mode
        self._settings.show_float_window = self._float_cb.isChecked()
        self._settings.reduce_motion = self._motion_cb.isChecked()
        self._settings.close_to_tray = self._tray_rb.isChecked()
        self._settings.ask_save_each_time = self._ask_cb.isChecked()
        self._settings.default_save_path = self._draft_save_path
        self._settings.max_history = self._max_spin.value()
        self._settings.max_file_mib = self._max_file_spin.value()
        self._settings.max_batch_items = self._max_batch_spin.value()
        self._settings.max_pdf_pages = self._max_pdf_spin.value()
        self._settings.max_zip_mib = self._max_zip_spin.value()
        self._settings.sync()
        self._theme.set_mode(mode)
        self._committed = True

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择默认保存路径", self._draft_save_path)
        if path:
            self._draft_save_path = path
            self._path_lbl.setText(path)

    def _clear_history(self):
        parent = self.parent()
        if not hasattr(parent, "history_mgr") or not parent.history_mgr.entries:
            return
        answer = QMessageBox.question(
            self,
            "清空历史记录",
            "将删除所有历史元数据，不会删除已导出的 Markdown 文件。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        parent.history_mgr.clear()
        if hasattr(parent, "_refresh_history"):
            parent._refresh_history()

    def reject(self) -> None:
        if not self._committed:
            self._theme.set_mode(self._snapshot["theme_mode"])
            parent = self.parent()
            if hasattr(parent, "_theme_btn"):
                parent._theme_btn.set_reduced_motion(self._snapshot["reduce_motion"])
            if self._float_win:
                self._float_win.set_reduced_motion(self._snapshot["reduce_motion"])
            if self._float_win:
                if self._snapshot["float_visible"]:
                    self._float_win.show()
                else:
                    self._float_win.hide()
        super().reject()
