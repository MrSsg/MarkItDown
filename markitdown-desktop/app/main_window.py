# SPDX-License-Identifier: MIT
"""Professional, keyboard-friendly two-pane desktop workspace."""

from __future__ import annotations

import html
import os
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QScrollArea,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.__about__ import __app_name__, __version__
from .history import HistoryEntry, HistoryManager
from .job_widgets import JobList
from .jobs import JobController, JobFailure, JobItem, ResourceLimits, SessionStore
from .ocr import OcrComponentManager
from .theme_toggle import ThemeToggleButton
from .ui_state import WorkspaceMode
from .widgets import HistoryPanel
from .worker import ConvertWorker


SUPPORTED_FILTER = (
    "所有支持的文件 (*.pdf *.docx *.pptx *.xlsx *.xls *.html *.htm *.txt *.csv "
    "*.json *.xml *.md *.jpg *.jpeg *.png *.wav *.mp3 *.m4a *.msg *.epub *.zip *.rtf);;"
    "所有文件 (*)"
)


class MainWindow(QMainWindow):
    workspace_mode_changed = Signal(str)
    job_summary_changed = Signal(str)

    def __init__(self, settings, theme_mgr, history_mgr) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumSize(720, 420)
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
        self._workspace_mode: WorkspaceMode | None = None
        self._queue_collapsed = False
        self._workspace_reflow_pending = False
        self._splitter_clamp_pending = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_current_timeout)
        self._build_ui()
        self._connect_signals()
        self._update_minimum_height()
        self._refresh_ocr_status()
        self._refresh_history()
        self._set_empty_detail()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        geometry = self._settings.window_geometry
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 800)
        self._apply_workspace_mode(self._mode_for_width(self.width()))

    def _resource_limits(self) -> ResourceLimits:
        return ResourceLimits(
            max_file_bytes=self._settings.max_file_mib * 1024 * 1024,
            max_batch_items=self._settings.max_batch_items,
            max_pdf_pages=self._settings.max_pdf_pages,
            max_zip_uncompressed_bytes=self._settings.max_zip_mib * 1024 * 1024,
        )

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        brand = QLabel("M")
        brand.setObjectName("brandMark")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFixedSize(36, 36)
        brand.setAccessibleName("MarkItDownDesk")
        header.addWidget(brand)
        title = QLabel("MarkItDownDesk")
        title.setObjectName("workspaceTitle")
        header.addWidget(title)
        self._workspace_subtitle = QLabel("批量转换工作台")
        self._workspace_subtitle.setObjectName("workspaceSubtitle")
        header.addWidget(self._workspace_subtitle)
        header.addStretch()
        self._queue_toggle_btn = QPushButton("收起队列")
        self._queue_toggle_btn.setObjectName("secondaryBtn")
        self._queue_toggle_btn.setToolTip("在窄窗口中切换任务队列")
        self._import_btn = QPushButton("导入文件")
        self._import_btn.setObjectName("headerImport")
        self._history_btn = QPushButton("历史")
        self._history_btn.setCheckable(True)
        self._history_btn.setAccessibleName("打开或关闭转换历史")
        self._settings_btn = QPushButton("设置")
        self._header_more_btn = QToolButton()
        self._header_more_btn.setText("更多")
        self._header_more_btn.setObjectName("headerMore")
        self._header_more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._header_more_btn.setAccessibleName("更多工作台操作")
        header_menu = QMenu(self._header_more_btn)
        self._header_queue_action = header_menu.addAction("显示/收起队列")
        self._header_history_action = header_menu.addAction("打开历史")
        self._header_settings_action = header_menu.addAction("打开设置")
        self._header_more_btn.setMenu(header_menu)
        self._theme_btn = ThemeToggleButton()
        self._theme_btn.set_theme(self._theme.current_theme, animate=False)
        self._theme_btn.set_accent_color(self._theme.colors.brand)
        self._theme_btn.set_reduced_motion(self._settings.reduce_motion)
        for button in (
            self._queue_toggle_btn,
            self._import_btn,
            self._history_btn,
            self._settings_btn,
            self._header_more_btn,
            self._theme_btn,
        ):
            button.setAccessibleName(button.text() or "切换主题")
            header.addWidget(button)
        layout.addLayout(header)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("workspaceSplitter")
        self._splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._splitter.setChildrenCollapsible(True)
        self._queue_content = self._build_queue_pane()
        self._queue_pane = QFrame()
        self._queue_pane.setObjectName("queuePane")
        self._queue_pane.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        queue_layout = QVBoxLayout(self._queue_pane)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)
        self._detail_pane = self._build_detail_pane()
        self._queue_scroll = QScrollArea()
        self._queue_scroll.setObjectName("queueScroll")
        self._queue_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._queue_scroll.setWidgetResizable(True)
        self._queue_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._queue_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._queue_scroll.setWidget(self._queue_content)
        queue_layout.addWidget(self._queue_scroll, 1)
        self._queue_controls = self._build_queue_controls()
        queue_layout.addWidget(self._queue_controls, 0)
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setObjectName("detailScroll")
        self._detail_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._detail_scroll.setWidget(self._detail_pane)
        self._detail_pane.setMinimumHeight(self._detail_pane.minimumSizeHint().height())
        self._splitter.addWidget(self._queue_pane)
        self._splitter.addWidget(self._detail_scroll)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, False)
        layout.addWidget(self._splitter, 1)

        self._status = QLabel("就绪")
        self._status.setObjectName("statusLine")
        self._status.setAccessibleName("工作台状态")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)

        self._history_dock = QDockWidget("转换历史", self)
        self._history_dock.setObjectName("historyDrawer")
        self._hist_panel = HistoryPanel()
        self._history_dock.setWidget(self._hist_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._history_dock)
        self._history_dock.hide()
        self._history_btn.setChecked(False)

    def _build_queue_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("queueContent")
        pane.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(9)

        title_row = QHBoxLayout()
        title = QLabel("任务队列")
        title.setObjectName("paneTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._queue_summary = QLabel("0 项")
        self._queue_summary.setObjectName("queueSummary")
        self._queue_summary.setWordWrap(False)
        self._queue_summary.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._queue_summary.setMinimumWidth(0)
        title_row.addWidget(self._queue_summary)
        layout.addLayout(title_row)

        hint = QLabel("拖放文件或点击添加。超限项目会在开始前标记失败。")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._drop_hint = QPushButton("＋ 添加文件")
        self._drop_hint.setObjectName("dropZone")
        self._drop_hint.setMinimumHeight(72)
        self._drop_hint.setAccessibleName("添加待转换文件")
        layout.addWidget(self._drop_hint)

        self._ocr_group = QFrame()
        self._ocr_group.setObjectName("optionsPane")
        options_layout = QHBoxLayout(self._ocr_group)
        options_layout.setContentsMargins(10, 8, 10, 8)
        self._ocr_cb = QCheckBox("启用离线 OCR")
        self._ocr_cb.setAccessibleName("当前批次启用离线 OCR")
        self._ocr_status = QLabel()
        self._ocr_status.setObjectName("mutedText")
        self._ocr_status.setWordWrap(True)
        self._ocr_install_btn = QPushButton("安装 OCR")
        self._ocr_install_btn.setObjectName("secondaryBtn")
        self._ocr_install_btn.setAccessibleName("安装或管理离线 OCR 组件")
        options_layout.addWidget(self._ocr_cb)
        options_layout.addWidget(self._ocr_status, 1)
        options_layout.addWidget(self._ocr_install_btn)
        layout.addWidget(self._ocr_group)

        self._job_list = JobList()
        self._job_list.setObjectName("jobList")
        self._job_list.refresh([])
        layout.addWidget(self._job_list, 1)

        return pane

    def _build_queue_controls(self) -> QWidget:
        controls_pane = QFrame()
        controls_pane.setObjectName("queueControls")
        controls = QVBoxLayout(controls_pane)
        controls.setContentsMargins(16, 8, 16, 12)
        controls.setSpacing(8)
        row = QHBoxLayout()
        self._start_btn = QPushButton("开始转换")
        self._start_btn.setObjectName("primaryAction")
        self._start_btn.setAccessibleName("开始转换当前队列")
        self._cancel_btn = QPushButton("取消后续")
        self._cancel_btn.setObjectName("secondaryBtn")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setAccessibleName("取消尚未开始的任务")
        row.addWidget(self._start_btn)
        row.addWidget(self._cancel_btn)
        controls.addLayout(row)
        self._retry_btn = QPushButton("重试失败项")
        self._retry_btn.setObjectName("secondaryBtn")
        self._retry_btn.setEnabled(False)
        self._retry_btn.setAccessibleName("重试全部可重试失败项")
        controls.addWidget(self._retry_btn)
        return controls_pane

    def _build_detail_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("detailPane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        self._detail_title = QLabel("结果详情")
        self._detail_title.setObjectName("paneTitle")
        self._detail_title.setWordWrap(True)
        title_row.addWidget(self._detail_title, 1)
        self._detail_status = QLabel("未选择")
        self._detail_status.setObjectName("statusBadge")
        self._detail_status.setProperty("status", "warning")
        title_row.addWidget(self._detail_status)
        layout.addLayout(title_row)
        self._detail_meta = QLabel("从左侧队列选择任务，或先添加文件。")
        self._detail_meta.setObjectName("mutedText")
        self._detail_meta.setWordWrap(True)
        layout.addWidget(self._detail_meta)

        progress_row = QHBoxLayout()
        self._progress_meta = QLabel("等待任务")
        self._progress_meta.setObjectName("progressMeta")
        self._progress_meta.setAccessibleName("转换进度说明")
        progress_row.addWidget(self._progress_meta, 1)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setAccessibleName("批次转换进度")
        progress_row.addWidget(self._progress, 1)
        layout.addLayout(progress_row)

        toolbar = QHBoxLayout()
        self._view_mode_btn = QPushButton("查看源码")
        self._copy_btn = QPushButton("复制")
        self._save_btn = QPushButton("导出当前")
        for button in (self._view_mode_btn, self._copy_btn, self._save_btn):
            button.setObjectName("secondaryBtn")
            toolbar.addWidget(button)
        self._more_btn = QToolButton()
        self._more_btn.setText("更多")
        self._more_btn.setObjectName("moreButton")
        self._more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more_btn.setAccessibleName("更多结果操作")
        menu = QMenu(self._more_btn)
        self._export_all_action = menu.addAction("导出全部")
        self._pin_action = menu.addAction("固定结果")
        menu.addSeparator()
        self._unpin_all_action = menu.addAction("全部取消固定")
        self._retry_current_action = menu.addAction("重试当前任务")
        self._failure_action = menu.addAction("查看失败日志")
        self._more_btn.setMenu(menu)
        toolbar.addWidget(self._more_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(True)
        self._preview.setObjectName("markdownPreview")
        self._preview.setAccessibleName("Markdown 结果预览")
        layout.addWidget(self._preview, 1)
        return pane

    def _connect_signals(self) -> None:
        self._import_btn.clicked.connect(self._open_file)
        self._drop_hint.clicked.connect(self._open_file)
        self._queue_toggle_btn.clicked.connect(self._toggle_queue)
        self._header_queue_action.triggered.connect(self._toggle_queue)
        self._start_btn.clicked.connect(self._start_convert)
        self._cancel_btn.clicked.connect(self._cancel_queue)
        self._retry_btn.clicked.connect(self._retry_failed)
        self._failure_action.triggered.connect(self._show_failure_report)
        self._retry_current_action.triggered.connect(self._retry_current)
        self._history_btn.clicked.connect(self._toggle_history_dock)
        self._settings_btn.clicked.connect(self._open_settings)
        self._header_history_action.triggered.connect(self._toggle_history_dock)
        self._header_settings_action.triggered.connect(self._open_settings)
        self._theme_btn.clicked.connect(self._theme.toggle)
        self._ocr_cb.toggled.connect(self._on_ocr_toggled)
        self._ocr_install_btn.clicked.connect(self._open_ocr_install)
        self._view_mode_btn.clicked.connect(self._toggle_preview_mode)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        self._save_btn.clicked.connect(self._save_file)
        self._export_all_action.triggered.connect(lambda: self._save_file(batch=True))
        self._pin_action.triggered.connect(self._toggle_pin_current_result)
        self._unpin_all_action.triggered.connect(self._unpin_all_results)
        self._hist_panel.clear_btn.clicked.connect(self._clear_history)
        self._hist_panel.item_selected.connect(self._on_history_selected)
        self._hist_panel.item_activated.connect(self._on_history_activated)
        self._job_list.item_selected.connect(self._on_job_selected)
        self._job_list.item_activated.connect(self._on_job_selected)
        self._worker.finished.connect(self._on_convert_finished)
        self._worker.error.connect(self._on_convert_error)
        self._worker.progress.connect(self._on_convert_progress)
        self._worker.started.connect(self._on_convert_started)
        self._worker.ocr_unavailable.connect(self._on_ocr_unavailable)
        self._theme.theme_changed.connect(self._on_theme_changed)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._history_dock.visibilityChanged.connect(self._on_history_visibility_changed)

    def _toggle_history_dock(self) -> None:
        if self._history_dock.isVisible():
            self._history_dock.hide()
        else:
            self._history_dock.show()
            self._history_dock.raise_()

    def _on_history_visibility_changed(self, visible: bool) -> None:
        self._history_btn.setChecked(visible)
        self._history_btn.setAccessibleName(
            "关闭转换历史" if visible else "打开转换历史"
        )
        self._header_history_action.setText("关闭历史" if visible else "打开历史")

    def _refresh_ocr_status(self) -> None:
        info = self._ocr_manager.status()
        if info.installed:
            self._ocr_status.setText(f"已安装 v{info.version} · 本机处理")
            self._ocr_install_btn.setText("管理 OCR")
        else:
            self._ocr_status.setText("未安装 · 安装后可用")
            self._ocr_install_btn.setText("安装 OCR")

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
        self._theme_btn.set_accent_color(self._theme.colors.brand)
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
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._on_files_dropped(paths)
            event.acceptProposedAction()

    def _on_files_dropped(self, paths: list[str]) -> None:
        if self._jobs.state.value in ("Running", "Cancelling", "TimedOutWaiting"):
            self._announce("当前批次正在运行，完成后再创建新任务")
            return
        if self._jobs.items:
            answer = QMessageBox.question(
                self,
                "替换当前队列",
                "当前队列和会话结果将被替换。已导出或固定的文件不会删除。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        old_store = self._jobs.store
        self._jobs = JobController(self._resource_limits())
        old_store.cleanup()
        self._jobs.enqueue(paths)
        self._refresh_jobs()
        rejected = len(self._jobs.failures)
        self._announce(
            f"已创建 {len(self._jobs.items)} 个任务"
            + (f"，{rejected} 个预检失败" if rejected else "")
        )

    def _summary_text(self) -> str:
        items = self._jobs.items
        if not items:
            return "0 项"
        success = sum(item.state == "success" for item in items)
        failed = sum(item.state == "error" for item in items)
        running = sum(item.state == "running" for item in items)
        queued = sum(item.state == "queued" for item in items)
        parts = [f"共 {len(items)} 项", f"已完成 {success}"]
        if running:
            parts.append(f"进行中 {running}")
        if queued:
            parts.append(f"等待 {queued}")
        if failed:
            parts.append(f"失败 {failed}")
        return " · ".join(parts)

    def _refresh_jobs(self) -> None:
        self._job_list.refresh(self._jobs.items)
        self._job_list.setVisible(True)
        busy = self._jobs.state.value in ("Running", "Cancelling", "TimedOutWaiting")
        self._retry_btn.setEnabled(bool(self._jobs.failures) and not busy)
        self._failure_action.setEnabled(bool(self._jobs.failures))
        self._start_btn.setEnabled(bool(self._jobs.items) and not busy)
        self._cancel_btn.setEnabled(self._jobs.state.value in ("Running", "TimedOutWaiting"))
        self._queue_summary.setText(self._summary_text())
        self._queue_summary.setToolTip(self._summary_text())
        self._retry_current_action.setEnabled(self._selected_item() is not None and bool(self._selected_item().failure))
        self._refresh_pin_actions()
        summary = self._summary_text()
        self.job_summary_changed.emit(summary)
        if self._float_win is not None:
            self._float_win.set_status_summary(summary)

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
        self._set_detail_status("转换中", "warning")
        self._detail_meta.setText("正在准备转换…")
        self._progress_meta.setText(f"当前文件：{item.file_name}")
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
            self._announce("OCR 超时，正在停止 OCR 子进程")
            return
        self._jobs.mark_timeout_waiting()
        self._announce("转换超过 10 分钟，等待当前线程自然结束")
        self._refresh_jobs()

    def _cancel_queue(self) -> None:
        self._jobs.request_cancel()
        self._announce("已取消后续任务；当前任务会安全完成")
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
        self._announce(f"转换失败：{os.path.basename(file_path)}，队列将继续")
        self._refresh_jobs()
        if next_item:
            self._start_item(next_item)
        else:
            self._finish_queue()

    @Slot(str, str)
    def _on_convert_started(self, _path: str, name: str) -> None:
        self._announce(f"正在转换：{name}")

    @Slot(object)
    def _on_convert_progress(self, event: object) -> None:
        if not isinstance(event, dict):
            self._progress_meta.setText(str(event))
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
        stage = str(event.get("stage", event.get("phase", "conversion")))
        stage_label = "OCR 识别" if stage.lower() in {"ocr", "recognition"} else "转换"
        suffix = f" · 第 {page} 页" if page else ""
        self._progress.setRange(0, 100)
        self._progress.setValue(percent)
        self._progress_meta.setText(
            f"{stage_label} {current}/{total}{suffix} · 剩余 {remaining} 项"
        )
        self._announce(f"{stage_label}进度 {percent}%")

    def _finish_queue(self) -> None:
        self._worker.close_ocr_engine()
        self._progress.setRange(0, 100)
        self._progress.setValue(100 if self._jobs.completed_count else 0)
        if self._jobs.failures:
            text = f"批次完成：成功 {self._jobs.completed_count}，失败 {len(self._jobs.failures)}"
            self._set_detail_status("有失败项", "error")
        else:
            text = f"批次完成：成功 {self._jobs.completed_count}"
            self._set_detail_status("已完成", "success")
        self._progress_meta.setText(text)
        self._announce(text)
        self._refresh_jobs()

    def _retry_failed(self) -> None:
        items = self._jobs.retry_failures()
        self._refresh_jobs()
        if items:
            self._start_convert()

    def _retry_current(self) -> None:
        selected = self._selected_item()
        if not selected or not selected.failure:
            return
        if self._jobs.state.value in ("Running", "Cancelling", "TimedOutWaiting"):
            self._announce("当前批次正在运行，完成后才能重试")
            return
        item = self._jobs.retry_item(selected.file_path)
        if item is None:
            self._announce("当前失败项不可重试")
            return
        self._refresh_jobs()
        self._start_convert()

    def _show_failure_report(self) -> None:
        entries = []
        for item in self._jobs.failures:
            failure = item.failure
            if failure:
                entries.append(f"{item.file_name}\n[{failure.code}] {failure.message}\n{failure.detail}".strip())
        if not entries:
            return
        log_entries = [self._jobs.store.read_log(item.log_path) for item in self._jobs.failures]
        dialog = QDialog(self)
        dialog.setWindowTitle("批量转换失败日志")
        dialog.setMinimumSize(720, 480)
        layout = QVBoxLayout(dialog)
        summary = QLabel(f"共 {len(entries)} 个任务失败。可复制日志或重试失败项。")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setAccessibleName("失败任务完整日志")
        editor.setPlainText("\n\n".join(entries + [entry for entry in log_entries if entry]))
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_button = buttons.addButton("复制完整日志", QDialogButtonBox.ButtonRole.ActionRole)
        retry_button = buttons.addButton("重试失败项", QDialogButtonBox.ButtonRole.ActionRole)
        open_button = buttons.addButton("打开日志目录", QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        retry_button.clicked.connect(lambda: (dialog.accept(), self._retry_failed()))
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._jobs.store.logs_path))))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _selected_item(self) -> JobItem | None:
        current = self._job_list.currentItem()
        if not current:
            return None
        path = str(current.data(Qt.ItemDataRole.UserRole))
        return next((value for value in self._jobs.items if value.file_path == path), None)

    def _on_job_selected(self, path: str) -> None:
        item = next((value for value in self._jobs.items if value.file_path == path), None)
        if not item:
            return
        self._current_file = path
        self._detail_title.setText(item.file_name)
        self._retry_current_action.setEnabled(bool(item.failure))
        if item.result_path:
            self._current_markdown = self._jobs.store.read(item.result_path)
            self._show_markdown(item, self._current_markdown)
        elif item.failure:
            self._set_detail_status("失败", "error")
            self._detail_meta.setText(f"[{item.failure.code}] {item.failure.message}")
            self._preview.setPlainText(
                f"{item.failure.message}\n\n下一步：可复制失败日志，或使用“更多 → 重试当前任务”。\n\n{item.failure.detail}".strip()
            )
        elif item.state == "running":
            self._set_detail_status("转换中", "warning")
            self._detail_meta.setText("正在处理此文件…")
        else:
            self._set_detail_status("等待中", "warning")
            self._detail_meta.setText("等待转换")
            self._preview.clear()
        self._refresh_pin_actions()

    def _show_markdown(self, item: JobItem, markdown: str) -> None:
        self._set_detail_status("已完成", "success")
        self._detail_meta.setText(
            f"已转换 · 结果仅在本次会话中缓存：{item.result_path.name if item.result_path else ''}"
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

            body = markdown_lib.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
        except ImportError:
            body = f"<pre>{html.escape(text)}</pre>"
        colors = self._theme.colors
        self._preview.setHtml(
            f"<style>body{{background:{colors.bg};color:{colors.primary_text};font:14px 'Microsoft YaHei','Segoe UI';line-height:1.6}}"
            f"pre,code{{background:{colors.card_hover};border:1px solid {colors.border};padding:8px}}"
            f"table{{border-collapse:collapse}}td,th{{border:1px solid {colors.border};padding:6px}}a{{color:{colors.brand_text}}}</style>{body}"
        )

    def _save_file(self, batch: bool = False) -> None:
        if batch:
            available = [item for item in self._jobs.items if item.result_path]
            if not available:
                self._announce("当前没有可导出的结果")
                return
            folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
            if not folder:
                return
            targets = [os.path.join(folder, os.path.splitext(item.file_name)[0] + ".md") for item in available]
            existing = [target for target in targets if os.path.exists(target)]
            if existing:
                answer = QMessageBox.question(
                    self,
                    "覆盖已有文件",
                    f"有 {len(existing)} 个目标文件已存在，是否覆盖？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            success = 0
            failures = []
            for item, target in zip(available, targets):
                try:
                    PathLike.write(target, self._jobs.store.read(item.result_path))
                    self.history_mgr.mark_export(item.file_path, target)
                    success += 1
                except OSError as exc:
                    failures.append(f"{item.file_name}: {exc}")
            self._announce(f"已导出 {success}/{len(available)} 个文件" + (f"，失败 {len(failures)} 个" if failures else ""))
            if failures:
                self._detail_meta.setText("批量导出部分失败：\n" + "\n".join(failures))
            return
        if not self._current_markdown:
            self._announce("当前没有可导出的结果")
            return
        name = os.path.splitext(os.path.basename(self._current_file or "output"))[0] + ".md"
        target, _ = QFileDialog.getSaveFileName(self, "导出 Markdown", name, "Markdown (*.md)")
        if target:
            try:
                PathLike.write(target, self._current_markdown)
                self.history_mgr.mark_export(self._current_file or "", target)
                self._announce(f"已导出：{target}")
            except OSError as exc:
                self._announce(f"导出失败：{exc}")

    def _pin_current_result(self) -> None:
        item = next((entry for entry in self._jobs.items if entry.file_path == self._current_file), None)
        if item is None or item.result_path is None:
            self._announce("当前没有可固定的转换结果")
            return
        try:
            item.pinned_path = self._jobs.store.pin(item.result_path, item.file_name)
            self.history_mgr.mark_pinned(item.file_path, str(item.pinned_path))
            self._announce(f"结果已固定：{item.pinned_path.name}")
            self._refresh_history()
            self._refresh_pin_actions()
        except OSError as exc:
            self._announce(f"固定结果失败：{exc}")

    def _current_pinned_path(self) -> Path | None:
        if not self._current_file:
            return None
        item = next(
            (entry for entry in self._jobs.items if entry.file_path == self._current_file),
            None,
        )
        if item and item.pinned_path:
            return Path(item.pinned_path)
        for entry in self.history_mgr.entries:
            if entry.file_path == self._current_file and entry.pinned_path:
                return Path(entry.pinned_path)
        return None

    def _refresh_pin_actions(self) -> None:
        if not hasattr(self, "_pin_action"):
            return
        current_item = next(
            (entry for entry in self._jobs.items if entry.file_path == self._current_file),
            None,
        )
        pinned = self._current_pinned_path()
        self._pin_action.setText("取消固定" if pinned else "固定结果")
        self._pin_action.setEnabled(bool(pinned) or bool(current_item and current_item.result_path))
        entries = getattr(self.history_mgr, "pinned_entries", None)
        if entries is None:
            entries = [entry for entry in self.history_mgr.entries if entry.pinned_path]
        self._unpin_all_action.setEnabled(bool(entries))

    def _toggle_pin_current_result(self) -> None:
        if not self._current_file:
            self._announce("当前没有可固定的转换结果")
            return
        if self._current_pinned_path() is not None:
            self.history_mgr.unpin(self._current_file)
            item = next(
                (entry for entry in self._jobs.items if entry.file_path == self._current_file),
                None,
            )
            if item:
                item.pinned_path = None
            self._announce("已取消固定当前结果")
            self._refresh_history()
            self._refresh_jobs()
            return
        self._pin_current_result()

    def _unpin_all_results(self) -> None:
        entries = getattr(self.history_mgr, "pinned_entries", None)
        if entries is None:
            entries = [entry for entry in self.history_mgr.entries if entry.pinned_path]
        if not entries:
            self._announce("当前没有已固定的结果")
            return
        answer = QMessageBox.question(
            self,
            "全部取消固定",
            f"将取消固定并删除 {len(entries)} 个固定结果文件；已导出的文件不会删除。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        paths = self.history_mgr.clear_pins()
        for item in self._jobs.items:
            if item.pinned_path:
                item.pinned_path = None
        self._announce(f"已全部取消固定（{len(paths)} 个结果）")
        self._refresh_history()
        self._refresh_jobs()

    def _copy_to_clipboard(self) -> None:
        if self._current_markdown:
            QApplication.clipboard().setText(self._current_markdown)
            self._announce("已复制到剪贴板")

    def _open_settings(self) -> None:
        from .dialogs import SettingsDialog

        SettingsDialog(self._settings, self._theme, self._float_win, self).exec()
        self._jobs.limits = self._resource_limits()
        self._refresh_ocr_status()
        self._refresh_history()

    def _refresh_history(self) -> None:
        self._hist_panel.list_widget.clear()
        entries = self.history_mgr.entries
        for entry in entries:
            marker = " · 已固定" if entry.pinned_path else ""
            item = self._hist_panel.list_widget.addItem(
                f"{entry.file_name}  ·  {time.strftime('%Y-%m-%d %H:%M', time.localtime(entry.timestamp))}{marker}"
            )
            # QListWidget.addItem returns None; attach paths and the full metadata separately.
        for index, entry in enumerate(entries):
            row = self._hist_panel.list_widget.item(index)
            row.setData(Qt.ItemDataRole.UserRole, entry.file_path)
            row.setData(Qt.ItemDataRole.UserRole + 1, entry)
            row.setToolTip(self._history_tooltip(entry))
        self._hist_panel.set_count(len(entries))
        self._refresh_pin_actions()

    @staticmethod
    def _history_tooltip(entry: HistoryEntry) -> str:
        durable = entry.pinned_path or entry.export_path
        if entry.pinned_path:
            state = "已固定结果"
        elif durable:
            state = "已有导出结果"
        else:
            state = "仅保存源文件定位，激活后可重新转换"
        return f"{entry.file_name}\n{state}"

    def _clear_history(self) -> None:
        if not self.history_mgr.entries:
            return
        answer = QMessageBox.question(
            self,
            "清空历史记录",
            "将删除所有历史元数据，不会删除已导出的 Markdown 文件。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history_mgr.clear()
            self._refresh_history()
            if self._float_win is not None:
                self._float_win.set_history_entries([])

    def _on_history_selected(self, item) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(entry, HistoryEntry):
            return
        self._history_dock.show()
        self._detail_title.setText(entry.file_name)
        self._set_detail_status("历史记录", "warning")
        self._detail_meta.setText("历史记录不会自动开始转换。按 Enter 或双击查看已有结果或重新转换。")
        durable = entry.pinned_path or entry.export_path
        self._preview.setPlainText(
            f"源文件：{entry.file_path}\n"
            f"类型：{entry.file_type or '未知'}\n"
            f"大小：{entry.file_size:,} 字节\n"
            f"结果：{durable if durable else '当前仅保存源文件定位'}"
        )
        self._current_file = entry.file_path
        self._refresh_pin_actions()

    def _on_history_activated(self, item) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(entry, HistoryEntry):
            return
        durable = next((path for path in (entry.pinned_path, entry.export_path) if path and os.path.isfile(path)), None)
        if durable:
            self._current_file = entry.file_path
            QDesktopServices.openUrl(QUrl.fromLocalFile(durable))
            self._announce(f"已打开历史结果：{os.path.basename(durable)}")
            self._refresh_pin_actions()
            return
        if not os.path.isfile(entry.file_path):
            self._announce("历史源文件已不存在，无法重新转换")
            return
        box = QMessageBox(self)
        box.setWindowTitle("重新转换历史文件")
        box.setText(f"没有可直接打开的持久结果：{entry.file_name}")
        box.setInformativeText("是否将它加入新的转换队列？当前队列不会被静默覆盖。")
        convert = box.addButton("重新转换", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is convert:
            self._history_dock.hide()
            self._on_files_dropped([entry.file_path])

    def _set_empty_detail(self) -> None:
        self._set_detail_status("未选择", "warning")
        self._detail_title.setText("结果详情")
        self._detail_meta.setText("从左侧队列选择任务，或先添加文件。")
        self._progress_meta.setText("等待任务")
        self._preview.setHtml(
            "<h3>开始一次转换</h3>"
            "<p>拖放 PDF、Office、图片或文本文件到左侧队列，然后点击“开始转换”。</p>"
            "<p>结果只在本次会话缓存；需要长期保留时请导出或固定结果。</p>"
        )
        self._refresh_pin_actions()

    def _set_detail_status(self, text: str, status: str) -> None:
        self._detail_status.setText(text)
        self._detail_status.setProperty("status", status)
        self._detail_status.style().unpolish(self._detail_status)
        self._detail_status.style().polish(self._detail_status)

    def _announce(self, text: str) -> None:
        self._status.setText(text)
        self._status.setToolTip(text)

    def _toggle_queue(self) -> None:
        if self._queue_collapsed:
            self._queue_collapsed = False
            if self._splitter.orientation() == Qt.Orientation.Vertical:
                total = self._splitter.height()
                queue_size = min(330, max(220, total - 200))
                self._splitter.setSizes([queue_size, max(200, total - queue_size)])
            else:
                self._size_horizontal_panes(self._workspace_mode)
            self._queue_toggle_btn.setText("收起队列")
            self._queue_toggle_btn.setAccessibleName("收起任务队列")
        else:
            self._queue_collapsed = True
            self._splitter.setSizes([0, self._splitter.width()])
            self._queue_toggle_btn.setText("显示队列")
            self._queue_toggle_btn.setAccessibleName("显示任务队列")

    @staticmethod
    def _mode_for_width(width: int) -> WorkspaceMode:
        if width >= 1100:
            return WorkspaceMode.WIDE
        if width >= 820:
            return WorkspaceMode.COMPACT
        return WorkspaceMode.STACKED

    def _apply_workspace_mode(self, mode: WorkspaceMode) -> None:
        same_mode = mode == self._workspace_mode and self._splitter.orientation() == (
            Qt.Orientation.Vertical if mode == WorkspaceMode.STACKED else Qt.Orientation.Horizontal
        )
        if same_mode:
            self._queue_toggle_btn.setVisible(
                mode == WorkspaceMode.COMPACT and self.width() >= 900
            )
            if mode == WorkspaceMode.STACKED and not self._queue_collapsed:
                self._size_stacked_panes()
            elif mode != WorkspaceMode.STACKED and not self._queue_collapsed:
                self._size_horizontal_panes(mode)
            self._schedule_workspace_reflow()
            return
        self._workspace_mode = mode
        stacked = mode == WorkspaceMode.STACKED
        self._splitter.setOrientation(Qt.Orientation.Vertical if stacked else Qt.Orientation.Horizontal)
        self._queue_toggle_btn.setVisible(
            mode == WorkspaceMode.COMPACT and self.width() >= 900
        )
        # Narrow windows cannot fit all low-frequency actions beside the brand.
        # Keep them reachable through one menu instead of letting QHBoxLayout clip.
        narrow_header = mode != WorkspaceMode.WIDE
        self._workspace_subtitle.setVisible(not narrow_header)
        self._history_btn.setVisible(not narrow_header)
        self._settings_btn.setVisible(not narrow_header)
        self._header_more_btn.setVisible(narrow_header)
        if stacked:
            self._queue_pane.setMaximumWidth(16777215)
            self._queue_pane.setMinimumHeight(0)
            self._detail_pane.setMinimumHeight(self._detail_pane.minimumSizeHint().height())
            if not self._queue_collapsed:
                self._size_stacked_panes()
        elif mode == WorkspaceMode.COMPACT:
            self._queue_pane.setMinimumWidth(
                max(300, self._queue_content.minimumSizeHint().width())
            )
            self._detail_pane.setMinimumWidth(440)
            if not self._queue_collapsed:
                self._size_horizontal_panes(mode)
        else:
            self._queue_pane.setMinimumWidth(
                max(340, self._queue_content.minimumSizeHint().width())
            )
            self._detail_pane.setMinimumWidth(560)
            if not self._queue_collapsed:
                self._size_horizontal_panes(mode)
        self.workspace_mode_changed.emit(mode.value)
        self._schedule_workspace_reflow()

    def _schedule_workspace_reflow(self) -> None:
        if self._workspace_reflow_pending:
            return
        self._workspace_reflow_pending = True
        QTimer.singleShot(0, self._reflow_workspace)

    def _reflow_workspace(self) -> None:
        self._workspace_reflow_pending = False
        mode = self._mode_for_width(self.width())
        if mode != self._workspace_mode:
            self._apply_workspace_mode(mode)
            return
        if self._queue_collapsed:
            return
        if mode == WorkspaceMode.STACKED:
            self._size_stacked_panes()
        else:
            self._size_horizontal_panes(mode)

    def _size_horizontal_panes(self, mode: WorkspaceMode | None) -> None:
        if mode == WorkspaceMode.STACKED or self._splitter.width() <= 0:
            return
        total = self._splitter.width()
        max_queue_size = max(1, total // 2)
        self._queue_pane.setMaximumWidth(16777215)
        if mode == WorkspaceMode.COMPACT:
            queue_size = min(420, max(300, round(total * 0.36)))
        else:
            queue_size = min(500, max(340, round(total * 0.32)))
        queue_size = min(queue_size, max_queue_size)
        self._splitter.setSizes([queue_size, max(0, total - queue_size)])

    def _on_splitter_moved(self, _position: int, _index: int) -> None:
        if self._splitter.orientation() != Qt.Orientation.Horizontal:
            return
        if self._splitter_clamp_pending:
            return
        total = self._splitter.width()
        if total <= 0:
            return
        sizes = self._splitter.sizes()
        max_queue_size = total // 2
        if not sizes or sizes[0] <= max_queue_size:
            return
        self._splitter_clamp_pending = True
        self._splitter.setSizes([max_queue_size, max(0, total - max_queue_size)])
        self._splitter_clamp_pending = False

    def _size_stacked_panes(self) -> None:
        total = max(1, self._splitter.height())
        detail_min = max(120, self._detail_scroll.minimumSizeHint().height())
        queue_required = (
            self._queue_content.sizeHint().height()
            + self._queue_controls.minimumSizeHint().height()
            + 4
        )
        detail_size = max(detail_min, int(total * 0.4))
        if queue_required + detail_size > total:
            detail_size = max(detail_min, total - queue_required)
        queue_size = max(220, total - detail_size)
        self._splitter.setSizes([queue_size, detail_size])

    def _update_minimum_height(self) -> None:
        queue_required = (
            self._queue_content.sizeHint().height()
            + self._queue_controls.minimumSizeHint().height()
            + 4
        )
        detail_required = max(120, self._detail_scroll.minimumSizeHint().height())
        # Header, status line, margins, spacings and splitter handle.
        overhead = 96
        self.setMinimumHeight(max(420, queue_required + detail_required + overhead))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_workspace_mode(self._mode_for_width(self.width()))

    def set_float_window(self, window) -> None:
        self._float_win = window
        self._float_win.set_status_summary(self._summary_text())

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
