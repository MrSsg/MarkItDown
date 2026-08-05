# SPDX-License-Identifier: MIT
"""Professional two-pane desktop workspace."""

from __future__ import annotations

import html
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QDialogButtonBox,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.__about__ import __app_name__, __version__
from .history import HistoryManager
from .job_widgets import JobList
from .jobs import JobController, JobFailure, JobItem, ResourceLimits, SessionStore
from .ocr import OcrComponentManager
from .theme_toggle import ThemeToggleButton
from .widgets import HistoryPanel
from .worker import ConvertWorker


SUPPORTED_FILTER = (
    "所有支持的文件 (*.pdf *.docx *.pptx *.xlsx *.xls *.html *.htm *.txt *.csv "
    "*.json *.xml *.md *.jpg *.jpeg *.png *.wav *.mp3 *.m4a *.msg *.epub *.zip *.rtf);;"
    "所有文件 (*)"
)


class MainWindow(QMainWindow):
    def __init__(self, settings, theme_mgr, history_mgr) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self._settings = settings
        self._theme = theme_mgr
        self.history_mgr = history_mgr
        SessionStore.cleanup_stale()
        self._jobs = JobController(self._resource_limits())
        self._worker = ConvertWorker(self)
        self._ocr_manager = OcrComponentManager()
        self._current_file: str | None = None
        self._current_markdown = ""
        self._float_win = None
        self._view_source = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_current_timeout)
        self._build_ui()
        self._connect_signals()
        self._refresh_ocr_status()
        self._refresh_history()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        geometry = self._settings.window_geometry
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 800)

    def _resource_limits(self) -> ResourceLimits:
        return ResourceLimits(
            max_file_bytes=self._settings.max_file_mib * 1024 * 1024,
            max_batch_items=self._settings.max_batch_items,
            max_pdf_pages=self._settings.max_pdf_pages,
            max_zip_uncompressed_bytes=self._settings.max_zip_mib * 1024 * 1024,
        )

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        brand = QLabel("M")
        brand.setObjectName("brandMark")
        brand.setAlignment(Qt.AlignCenter)
        brand.setFixedSize(36, 36)
        header.addWidget(brand)
        title = QLabel("MarkItDownDesk")
        title.setObjectName("workspaceTitle")
        header.addWidget(title)
        subtitle = QLabel("批量转换工作台")
        subtitle.setObjectName("workspaceSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        self._import_btn = QPushButton("导入文件")
        self._import_btn.setObjectName("primaryAction")
        self._history_btn = QPushButton("历史")
        self._settings_btn = QPushButton("设置")
        self._theme_btn = ThemeToggleButton()
        self._theme_btn.set_theme(self._theme.current_theme, animate=False)
        for button in (self._history_btn, self._settings_btn, self._theme_btn):
            button.setObjectName(button.objectName() or "secondaryBtn")
            header.addWidget(button)
        header.addWidget(self._import_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("workspaceSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_queue_pane())
        splitter.addWidget(self._build_detail_pane())
        splitter.setSizes([390, 890])
        layout.addWidget(splitter, 1)

        self._status = QLabel("就绪")
        self._status.setObjectName("statusLine")
        layout.addWidget(self._status)

        self._history_dock = QDockWidget("转换历史", self)
        self._history_dock.setObjectName("historyDrawer")
        self._hist_panel = HistoryPanel()
        self._history_dock.setWidget(self._hist_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._history_dock)
        self._history_dock.hide()

    def _build_queue_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("queuePane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("任务队列")
        title.setObjectName("paneTitle")
        layout.addWidget(title)
        hint = QLabel("拖入文件或点击导入。超限项目会在开始前标记失败。")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._drop_hint = QPushButton("＋ 添加文件")
        self._drop_hint.setObjectName("dropZone")
        self._drop_hint.setMinimumHeight(84)
        layout.addWidget(self._drop_hint)
        self._job_list = JobList()
        self._job_list.setObjectName("jobList")
        layout.addWidget(self._job_list, 1)
        controls = QHBoxLayout()
        self._start_btn = QPushButton("开始转换")
        self._start_btn.setObjectName("primaryAction")
        self._cancel_btn = QPushButton("取消后续")
        self._cancel_btn.setObjectName("secondaryBtn")
        self._cancel_btn.setEnabled(False)
        controls.addWidget(self._start_btn)
        controls.addWidget(self._cancel_btn)
        layout.addLayout(controls)
        self._retry_btn = QPushButton("重试失败项")
        self._retry_btn.setObjectName("secondaryBtn")
        self._retry_btn.setEnabled(False)
        layout.addWidget(self._retry_btn)
        return pane

    def _build_detail_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("detailPane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(20, 16, 20, 16)
        self._detail_title = QLabel("选择一个任务")
        self._detail_title.setObjectName("paneTitle")
        layout.addWidget(self._detail_title)
        self._detail_meta = QLabel("尚未开始转换")
        self._detail_meta.setObjectName("mutedText")
        self._detail_meta.setWordWrap(True)
        layout.addWidget(self._detail_meta)
        options = QHBoxLayout()
        self._ocr_cb = QCheckBox("启用离线 OCR")
        self._ocr_status = QLabel()
        self._ocr_status.setObjectName("mutedText")
        self._ocr_install_btn = QPushButton("管理 OCR 组件")
        self._ocr_install_btn.setObjectName("secondaryBtn")
        options.addWidget(self._ocr_cb)
        options.addWidget(self._ocr_status, 1)
        options.addWidget(self._ocr_install_btn)
        layout.addLayout(options)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        toolbar = QHBoxLayout()
        self._view_mode_btn = QPushButton("查看源码")
        self._copy_btn = QPushButton("复制")
        self._save_btn = QPushButton("导出当前")
        self._export_all_btn = QPushButton("导出全部")
        self._pin_btn = QPushButton("固定结果")
        self._failure_btn = QPushButton("失败日志")
        for button in (
            self._view_mode_btn,
            self._copy_btn,
            self._save_btn,
            self._export_all_btn,
            self._pin_btn,
            self._failure_btn,
        ):
            button.setObjectName("secondaryBtn")
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(True)
        self._preview.setObjectName("markdownPreview")
        layout.addWidget(self._preview, 1)
        return pane

    def _connect_signals(self) -> None:
        self._import_btn.clicked.connect(self._open_file)
        self._drop_hint.clicked.connect(self._open_file)
        self._start_btn.clicked.connect(self._start_convert)
        self._cancel_btn.clicked.connect(self._cancel_queue)
        self._retry_btn.clicked.connect(self._retry_failed)
        self._failure_btn.clicked.connect(self._show_failure_report)
        self._history_btn.clicked.connect(self._history_dock.show)
        self._settings_btn.clicked.connect(self._open_settings)
        self._theme_btn.clicked.connect(self._theme.toggle)
        self._ocr_cb.toggled.connect(self._on_ocr_toggled)
        self._ocr_install_btn.clicked.connect(self._open_ocr_install)
        self._view_mode_btn.clicked.connect(self._toggle_preview_mode)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        self._save_btn.clicked.connect(self._save_file)
        self._export_all_btn.clicked.connect(lambda: self._save_file(batch=True))
        self._pin_btn.clicked.connect(self._pin_current_result)
        self._hist_panel.clear_btn.clicked.connect(self._clear_history)
        self._hist_panel.list_widget.itemClicked.connect(self._on_history_clicked)
        self._job_list.item_selected.connect(self._on_job_selected)
        self._worker.finished.connect(self._on_convert_finished)
        self._worker.error.connect(self._on_convert_error)
        self._worker.progress.connect(self._on_convert_progress)
        self._worker.started.connect(self._on_convert_started)
        self._worker.ocr_unavailable.connect(self._on_ocr_unavailable)
        self._theme.theme_changed.connect(self._on_theme_changed)

    def _refresh_ocr_status(self) -> None:
        info = self._ocr_manager.status()
        if info.installed:
            self._ocr_status.setText(f"已安装 v{info.version}，本机执行")
            self._ocr_install_btn.setText("管理 OCR 组件")
        else:
            self._ocr_status.setText("未安装；图片与扫描 PDF 可用")
            self._ocr_install_btn.setText("安装 OCR 组件")

    def _on_ocr_toggled(self, checked: bool) -> None:
        if checked and not self._ocr_manager.status().installed:
            self._ocr_cb.blockSignals(True)
            self._ocr_cb.setChecked(False)
            self._ocr_cb.blockSignals(False)
            self._open_ocr_install()

    def _open_ocr_install(self) -> None:
        from .dialogs import OcrInstallDialog

        OcrInstallDialog(self._ocr_manager, self).exec()
        self._refresh_ocr_status()

    def _on_ocr_unavailable(self, message: str) -> None:
        self._ocr_cb.setChecked(False)
        self._status.setText(f"OCR 未启用：{message}")

    def _on_theme_changed(self, is_dark) -> None:
        self._theme_btn.set_theme(is_dark)
        if self._current_markdown and not self._view_source:
            self._render_markdown(self._current_markdown)

    def _open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择待转换文件", "", SUPPORTED_FILTER)
        if paths:
            self._on_files_dropped(paths)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        if paths:
            self._on_files_dropped(paths)
            event.acceptProposedAction()

    def _on_files_dropped(self, paths: list[str]) -> None:
        if self._jobs.state.value in ("Running", "Cancelling", "TimedOutWaiting"):
            self._status.setText("当前批次正在运行，完成后再创建新任务")
            return
        old_store = self._jobs.store
        self._jobs = JobController(self._resource_limits())
        old_store.cleanup()
        self._jobs.enqueue(paths)
        self._refresh_jobs()
        rejected = len(self._jobs.failures)
        self._status.setText(
            f"已创建 {len(self._jobs.items)} 个任务"
            + (f"，{rejected} 个预检失败" if rejected else "")
        )

    def _refresh_jobs(self) -> None:
        self._job_list.refresh(self._jobs.items)
        self._retry_btn.setEnabled(
            bool(self._jobs.failures)
            and self._jobs.state.value
            not in ("Running", "Cancelling", "TimedOutWaiting")
        )
        self._failure_btn.setEnabled(bool(self._jobs.failures))
        self._start_btn.setEnabled(
            bool(self._jobs.items) and self._jobs.state.value in ("Idle", "Completed")
        )
        self._cancel_btn.setEnabled(
            self._jobs.state.value in ("Running", "TimedOutWaiting")
        )

    def _start_convert(self) -> None:
        item = self._jobs.start()
        self._refresh_jobs()
        if item is None:
            self._finish_queue()
            return
        self._start_item(item)

    def _start_item(self, item: JobItem) -> None:
        self._current_file = item.file_path
        self._detail_title.setText(item.file_name)
        self._detail_meta.setText("正在转换…")
        self._progress.setRange(0, 0)
        if not self._worker.start_convert(
            item.file_path,
            self._ocr_cb.isChecked(),
            self._ocr_manager,
            request_id=item.request_id,
        ):
            self._jobs.fail_current(JobFailure("scheduler", "WORKER_BUSY", "转换器仍在运行"))
            self._start_convert()
            return
        timeout_ms = (
            5 * 60 * 1000
            if self._ocr_cb.isChecked() and PathSuffix.is_ocr_file(item.file_path)
            else 10 * 60 * 1000
        )
        self._timeout.start(timeout_ms)
        self._refresh_jobs()

    def _on_current_timeout(self) -> None:
        current = self._jobs.current
        if not current:
            return
        if self._ocr_cb.isChecked() and PathSuffix.is_ocr_file(current.file_path):
            self._worker.stop_owned_ocr_process()
            self._status.setText("OCR 超时，正在停止 OCR 子进程")
            return
        self._jobs.mark_timeout_waiting()
        self._status.setText("转换超过 10 分钟，等待当前线程自然结束")
        self._refresh_jobs()

    def _cancel_queue(self) -> None:
        self._jobs.request_cancel()
        self._status.setText("已取消后续任务；当前任务会安全完成")
        self._refresh_jobs()

    @Slot(str, str)
    def _on_convert_finished(self, markdown: str, file_path: str) -> None:
        self._timeout.stop()
        current = self._jobs.current
        next_item = self._jobs.complete_current(markdown)
        if current and current.state == "success":
            self._current_markdown = markdown
            self._show_markdown(current, markdown)
            self.history_mgr.add(HistoryManager.make_entry(file_path, markdown))
            self._refresh_history()
        self._refresh_jobs()
        if next_item:
            self._start_item(next_item)
        else:
            self._finish_queue()

    @Slot(object, str)
    def _on_convert_error(self, error: object, file_path: str) -> None:
        self._timeout.stop()
        payload = error if isinstance(error, dict) else {}
        failure = JobFailure(
            str(payload.get("stage", "conversion")),
            str(payload.get("code", "CONVERSION_FAILED")),
            str(payload.get("message", "转换失败")),
            str(payload.get("detail", error)),
        )
        next_item = self._jobs.fail_current(failure)
        self._status.setText(f"转换失败：{os.path.basename(file_path)}")
        self._refresh_jobs()
        if next_item:
            self._start_item(next_item)
        else:
            self._finish_queue()

    @Slot(str, str)
    def _on_convert_started(self, _path: str, name: str) -> None:
        self._status.setText(f"正在转换：{name}")

    @Slot(object)
    def _on_convert_progress(self, event: object) -> None:
        if not isinstance(event, dict):
            self._status.setText(str(event))
            self._progress.setRange(0, 0)
            return
        current = int(event.get("current", 0))
        total = int(event.get("total", 0))
        page = event.get("page")
        terminal = {"success", "error", "cancelled"}
        completed = sum(item.state in terminal for item in self._jobs.items)
        fraction = current / total if total else 0.0
        percent = round(100 * (completed + fraction) / max(len(self._jobs.items), 1))
        remaining = sum(item.state == "queued" for item in self._jobs.items)
        suffix = f"，第 {page} 页" if page else ""
        self._progress.setRange(0, 100)
        self._progress.setValue(percent)
        self._status.setText(f"OCR 识别中 {current}/{total}{suffix}，剩余 {remaining} 项")

    def _finish_queue(self) -> None:
        self._worker.close_ocr_engine()
        self._progress.setRange(0, 100)
        self._progress.setValue(100 if self._jobs.completed_count else 0)
        if self._jobs.failures:
            self._status.setText(
                f"批次完成：成功 {self._jobs.completed_count}，失败 {len(self._jobs.failures)}"
            )
        else:
            self._status.setText(f"批次完成：成功 {self._jobs.completed_count}")
        self._refresh_jobs()

    def _retry_failed(self) -> None:
        items = self._jobs.retry_failures()
        self._refresh_jobs()
        if items:
            self._start_convert()

    def _show_failure_report(self) -> None:
        entries = []
        for item in self._jobs.failures:
            failure = item.failure
            if failure:
                entries.append(
                    f"{item.file_name}\n[{failure.code}] {failure.message}\n{failure.detail}".strip()
                )
        if not entries:
            return
        log_entries = [
            self._jobs.store.read_log(item.log_path) for item in self._jobs.failures
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle("批量转换失败日志")
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"共 {len(entries)} 个任务失败"))
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(
            "\n\n".join(entries + [entry for entry in log_entries if entry])
        )
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton("复制完整日志", QDialogButtonBox.ActionRole)
        open_button = buttons.addButton("打开日志目录", QDialogButtonBox.ActionRole)
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(editor.toPlainText())
        )
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._jobs.store.logs_path))
            )
        )
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _on_job_selected(self, path: str) -> None:
        item = next(
            (value for value in self._jobs.items if value.file_path == path), None
        )
        if not item:
            return
        self._current_file = path
        self._detail_title.setText(item.file_name)
        if item.result_path:
            self._current_markdown = self._jobs.store.read(item.result_path)
            self._show_markdown(item, self._current_markdown)
        elif item.failure:
            self._detail_meta.setText(f"[{item.failure.code}] {item.failure.message}")
            self._preview.setPlainText(item.failure.detail or item.failure.message)
        else:
            self._detail_meta.setText("等待转换")
            self._preview.clear()

    def _show_markdown(self, item: JobItem, markdown: str) -> None:
        self._detail_meta.setText(
            f"已转换，结果仅在本次会话中缓存：{item.result_path.name if item.result_path else ''}"
        )
        if self._view_source:
            self._preview.setPlainText(markdown)
        else:
            self._render_markdown(markdown)

    def _toggle_preview_mode(self) -> None:
        self._view_source = not self._view_source
        self._view_mode_btn.setText("查看预览" if self._view_source else "查看源码")
        if self._current_markdown:
            self._on_job_selected(self._current_file or "")

    def _render_markdown(self, text: str) -> None:
        try:
            import markdown as markdown_lib

            body = markdown_lib.markdown(
                text, extensions=["fenced_code", "tables", "nl2br"]
            )
        except ImportError:
            body = f"<pre>{html.escape(text)}</pre>"
        colors = self._theme.colors
        self._preview.setHtml(
            f"<style>body{{background:{colors.bg};color:{colors.primary_text};font:14px 'Segoe UI';line-height:1.6}}"
            f"pre,code{{background:{colors.card_hover};border:1px solid {colors.border};padding:8px}}"
            f"table{{border-collapse:collapse}}td,th{{border:1px solid {colors.border};padding:6px}}a{{color:#407BFF}}</style>{body}"
        )

    def _save_file(self, batch: bool = False) -> None:
        if batch:
            available = [item for item in self._jobs.items if item.result_path]
            if not available:
                return
            folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
            if not folder:
                return
            success = 0
            for item in available:
                target = os.path.join(
                    folder, os.path.splitext(item.file_name)[0] + ".md"
                )
                try:
                    PathLike.write(target, self._jobs.store.read(item.result_path))
                    self.history_mgr.mark_export(item.file_path, target)
                    success += 1
                except OSError:
                    pass
            self._status.setText(f"已导出 {success}/{len(available)} 个文件")
            return
        if not self._current_markdown:
            return
        name = (
            os.path.splitext(os.path.basename(self._current_file or "output"))[0]
            + ".md"
        )
        target, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", name, "Markdown (*.md)"
        )
        if target:
            PathLike.write(target, self._current_markdown)
            self.history_mgr.mark_export(self._current_file or "", target)
            self._status.setText(f"已导出：{target}")

    def _pin_current_result(self) -> None:
        item = next(
            (
                entry
                for entry in self._jobs.items
                if entry.file_path == self._current_file
            ),
            None,
        )
        if item is None or item.result_path is None:
            self._status.setText("当前没有可固定的转换结果")
            return
        try:
            item.pinned_path = self._jobs.store.pin(item.result_path, item.file_name)
            self.history_mgr.mark_pinned(item.file_path, str(item.pinned_path))
            self._status.setText(f"结果已固定：{item.pinned_path.name}")
        except OSError as exc:
            self._status.setText(f"固定结果失败：{exc}")

    def _copy_to_clipboard(self) -> None:
        if self._current_markdown:
            QApplication.clipboard().setText(self._current_markdown)
            self._status.setText("已复制到剪贴板")

    def _open_settings(self) -> None:
        from .dialogs import SettingsDialog

        SettingsDialog(self._settings, self._theme, self._float_win, self).exec()
        self._jobs.limits = self._resource_limits()

    def _refresh_history(self) -> None:
        self._hist_panel.list_widget.clear()
        for entry in self.history_mgr.entries:
            item = self._hist_panel.list_widget.addItem(
                f"{entry.file_name}  ·  {time.strftime('%Y-%m-%d %H:%M', time.localtime(entry.timestamp))}"
            )
        # QListWidget.addItem returns None; attach paths in a second pass.
        for index, entry in enumerate(self.history_mgr.entries):
            self._hist_panel.list_widget.item(index).setData(
                Qt.UserRole, entry.file_path
            )
        self._hist_panel.set_count(len(self.history_mgr.entries))

    def _clear_history(self) -> None:
        self.history_mgr.clear()
        self._refresh_history()

    def _on_history_clicked(self, item) -> None:
        path = item.data(Qt.UserRole)
        if path and os.path.isfile(path):
            self._history_dock.hide()
            self._on_files_dropped([path])

    def set_float_window(self, window) -> None:
        self._float_win = window

    def closeEvent(self, event) -> None:
        self._settings.window_geometry = self.saveGeometry()
        self._settings.sync()
        if self._settings.close_to_tray:
            event.ignore()
            self.hide()
            return
        self._jobs.store.cleanup()
        QApplication.quit()


class PathSuffix:
    @staticmethod
    def is_ocr_file(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in {".pdf", ".jpg", ".jpeg", ".png"}


class PathLike:
    @staticmethod
    def write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(content)
