# SPDX-License-Identifier: MIT

import os, time, html as html_mod

from PySide6.QtCore import (Qt, Slot, QSize, QPropertyAnimation, QEvent,
    QEasingCurve, Signal)
from PySide6.QtGui import (QAction, QClipboard, QFont, QColor,
    QPainter, QPixmap, QIcon, QDragEnterEvent, QDropEvent,
    QDragLeaveEvent, QDragMoveEvent)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSplitter,
    QTextBrowser, QListWidget, QListWidgetItem, QLabel, QPushButton,
    QStatusBar, QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
    QRadioButton, QCheckBox, QSlider, QSpinBox, QComboBox, QFormLayout,
    QGroupBox, QSizePolicy, QApplication, QStyle, QGraphicsDropShadowEffect)

from .worker import ConvertWorker
from .history import HistoryManager, HistoryEntry
from .settings import AppSettings
from .theme import ThemeManager
from app.__about__ import __version__, __app_name__
TOPBAR_HEIGHT = 64
CARD_RADIUS = 16


from .widgets import TopBar, CollapsibleCard, DropArea, HistoryPanel, UploadPanel
from .dialogs import SettingsDialog


class ResettableSplitter(QSplitter):
    """QSplitter with double-click reset and hover cursor."""
    def __init__(self, orientation, default_sizes=None, parent=None):
        super().__init__(orientation, parent)
        self._default_sizes = default_sizes
        self.setHandleWidth(4)

    def showEvent(self, event):
        super().showEvent(event)
        for i in range(self.count()):
            self.handle(i).installEventFilter(self)

    def eventFilter(self, obj, event):
        for i in range(self.count()):
            if self.handle(i) is obj:
                if event.type() == QEvent.Type.Enter:
                    obj.setCursor(Qt.SplitHCursor if self.orientation() == Qt.Horizontal else Qt.SplitVCursor)
                elif event.type() == QEvent.Type.Leave:
                    obj.setCursor(Qt.ArrowCursor)
                elif event.type() == QEvent.Type.MouseButtonDblClick:
                    if self._default_sizes:
                        self.setSizes(self._default_sizes)
                    return True
                break
        return super().eventFilter(obj, event)

class MainWindow(QMainWindow):
    def __init__(self, settings, theme_mgr, history_mgr):
        super().__init__()
        self._settings = settings
        self._theme = theme_mgr
        self.history_mgr = history_mgr
        self._current_file = None
        self._current_markdown = ""
        self._convert_start = 0.0
        self._file_list = []
        self._conversion_results = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top Bar
        self._topbar = TopBar()
        root.addWidget(self._topbar)

        # Content area
        cw = QWidget()
        cw.setContentsMargins(16, 16, 16, 0)
        cl = QVBoxLayout(cw)
        cl.setSpacing(12)

        # Three equal-width cards in a horizontal splitter
        self._inner_splitter = ResettableSplitter(Qt.Horizontal, default_sizes=[333, 333, 334])

        # Card 1: Upload
        self._upload_card = CollapsibleCard("上传文件")
        self._upload_panel = UploadPanel()
        self._upload_card.content_layout().addWidget(self._upload_panel)
        self._upload_card.setMinimumWidth(220)
        self._inner_splitter.addWidget(self._upload_card)

        # Card 2: Options
        self._options_card = CollapsibleCard("转换选项")
        ol = self._options_card.content_layout()
        hl = QHBoxLayout()
        hl.addWidget(QLabel("标题层级:"))
        self._heading_cb = QComboBox()
        self._heading_cb.addItems(["h1", "h2", "h3", "h4", "h5", "h6"])
        self._heading_cb.setCurrentIndex(1)
        hl.addWidget(self._heading_cb); hl.addStretch()
        ol.addLayout(hl)
        self._render_cb = QCheckBox("渲染 Markdown 预览")
        self._render_cb.setChecked(True); ol.addWidget(self._render_cb)
        self._image_cb = QCheckBox("嵌入图片")
        self._image_cb.setChecked(True); ol.addWidget(self._image_cb)
        self._ocr_cb = QCheckBox("启用 OCR")
        ol.addWidget(self._ocr_cb)
        ol.addStretch()
        self._convert_btn = QPushButton("开始转换")
        self._convert_btn.setObjectName("primaryAction")
        self._convert_btn.setFixedHeight(44)
        ol.addWidget(self._convert_btn)
        self._options_card.setMinimumWidth(220)
        self._inner_splitter.addWidget(self._options_card)

        # Card 3: Preview
        self._preview_card = CollapsibleCard("Markdown 预览")
        pl = self._preview_card.content_layout()
        ptb = QHBoxLayout()
        self._view_mode_btn = QPushButton("预览")
        self._view_mode_btn.setObjectName("secondaryBtn")
        self._view_mode_btn.setFixedHeight(30)
        ptb.addWidget(self._view_mode_btn)
        self._copy_btn = QPushButton("📋 复制")
        self._copy_btn.setObjectName("secondaryBtn")
        self._copy_btn.setFixedHeight(30)
        ptb.addWidget(self._copy_btn)
        self._save_btn = QPushButton("导出")
        self._save_btn.setObjectName("secondaryBtn")
        self._save_btn.setFixedHeight(30)
        self._export_all_btn = QPushButton("导出全部")
        self._export_all_btn.setObjectName("secondaryBtn")
        self._export_all_btn.setFixedHeight(30)
        ptb.addWidget(self._save_btn)
        ptb.addWidget(self._export_all_btn); ptb.addStretch()
        pl.addLayout(ptb)
        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(True)
        pl.addWidget(self._preview)
        self._preview_card.setMinimumWidth(220)
        self._inner_splitter.addWidget(self._preview_card)

        # Wrap inner splitter + history into outer vertical splitter
        self._outer_splitter = ResettableSplitter(Qt.Vertical, default_sizes=[600, 400])
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._inner_splitter)

        self._hist_panel = HistoryPanel()
        self._hist_panel.setMinimumHeight(180)

        self._outer_splitter.addWidget(top_container)
        self._outer_splitter.addWidget(self._hist_panel)

        # Restore saved sizes
        saved_outer = self._settings.window_splitter_outer
        saved_inner = self._settings.window_splitter_inner
        if saved_outer:
            self._outer_splitter.restoreState(saved_outer)
        if saved_inner:
            self._inner_splitter.restoreState(saved_inner)

        root.addWidget(self._outer_splitter, 1)
        # Status Bar
        self._status = QLabel("就绪")
        self.statusBar().addWidget(self._status, 1)

        # Signals
        self._connect_signals()

        # Worker
        self._worker = ConvertWorker(self)
        self._worker.finished.connect(self._on_convert_finished)
        self._worker.error.connect(self._on_convert_error)
        self._worker.progress.connect(self._on_convert_progress)
        self._worker.started.connect(self._on_convert_started)
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        geo = self._settings.window_geometry
        if geo: self.restoreGeometry(geo)
        else: self.resize(1280, 800)
        self._refresh_history()

    def _connect_signals(self):
        self._topbar.tool_button("toolOpen").clicked.connect(self._open_file)
        self._topbar.tool_button("toolConvert").clicked.connect(self._start_convert)
        self._topbar.tool_button("toolCopy").clicked.connect(self._copy_to_clipboard)
        self._topbar.tool_button("toolClear").clicked.connect(self._clear_content)
        self._topbar.tool_button("toolMD").clicked.connect(self._toggle_preview_mode)
        self._topbar.theme_btn.clicked.connect(self._theme.toggle)
        self._topbar.settings_btn.clicked.connect(self._open_settings)
        self._upload_panel.files_added.connect(self._on_files_dropped)
        self._upload_panel.convert_requested.connect(self._start_convert)
        self._upload_panel._select_btn.clicked.connect(self._open_file)
        self._upload_panel.file_selected.connect(self._on_file_selected)
        self._convert_btn.clicked.connect(self._start_convert)
        self._view_mode_btn.clicked.connect(self._toggle_preview_mode)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        self._save_btn.clicked.connect(self._save_file)
        self._export_all_btn.clicked.connect(lambda: self._save_file(batch=True))
        self._hist_panel.clear_btn.clicked.connect(self._clear_history)
        self._hist_panel.list_widget.itemClicked.connect(self._on_history_clicked)
        self._theme.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme):
        self._topbar.update_theme_icon(theme == "dark")
        if self._current_markdown:
            self._render_markdown(self._current_markdown)

    def _open_file(self):
        filter_str = ("所有支持的文件 (*.pdf *.docx *.pptx *.xlsx *.xls "
            "*.html *.htm *.txt *.csv *.json *.xml *.md "
            "*.jpg *.jpeg *.png *.wav *.mp3 *.m4a "
            "*.msg *.epub *.zip *.rtf);;"
            "PDF (*.pdf);;Word (*.docx);;PowerPoint (*.pptx);;"
            "Excel (*.xlsx *.xls);;所有文件 (*)")
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filter_str)
        if path:
            self._on_files_dropped([path])

    def _on_files_dropped(self, paths):
        for p in paths:
            if os.path.isfile(p) and p not in self._file_list:
                self._file_list.append(p)
        self._refresh_file_list()
        self._status.setText(f"已加入 {len(self._file_list)} 个文件")
        self._status.setText(f"已加载 {len(self._file_list)} 个文件")

    def _refresh_file_list(self):
        self._upload_panel.clear_queue()
        for p in self._file_list:
            self._upload_panel.add_file(p)

    def _start_convert(self):
        if not self._file_list:
            QMessageBox.information(self, "提示", "请先添加文件。")
            return
        self._convert_file(self._file_list[0])

    def convert_file(self, file_path):
        self._convert_file(file_path)

    def _convert_file(self, file_path):
        self._current_file = file_path
        self._convert_start = time.time()
        self._worker.start_convert(file_path)

    def _on_file_selected(self, file_path):
        if file_path in self._conversion_results:
            self._current_file = file_path
            self._current_markdown = self._conversion_results[file_path]
            self._render_markdown(self._current_markdown)
            self._status.setText(f"预览: {os.path.basename(file_path)}")

    @Slot(str, str)
    def _on_convert_started(self, file_path, file_name):
        self._status.setText(f"正在转换: {os.path.basename(file_path)}...")
        self._convert_btn.setEnabled(False)
        self._convert_btn.setText("转换中...")

    @Slot(str)
    def _on_convert_progress(self, msg):
        self._status.setText(msg)

    @Slot(str, str)
    def _on_convert_finished(self, markdown, file_path):
        elapsed = time.time() - self._convert_start
        self._current_markdown = markdown
        self._convert_btn.setEnabled(True)
        self._convert_btn.setText("开始转换")
        self._status.setText(f"完成 ({elapsed:.1f}s)")
        self._render_markdown(markdown)
        self._conversion_results[file_path] = markdown
        entry = HistoryManager.make_entry(file_path, markdown)
        self.history_mgr.add(entry)
        self._refresh_history()

    @Slot(str, str)
    def _on_convert_error(self, error_msg, file_path):
        self._status.setText("转换失败")
        if hasattr(self, "_queue_index"):
            self._upload_panel.set_item_status(self._queue_index, "error")
            self._queue_index += 1
            self._process_next_in_queue()
        else:
            QMessageBox.warning(self, "转换失败", error_msg)

    def _toggle_preview_mode(self):
        txt = self._view_mode_btn.text()
        if txt == "预览":
            self._view_mode_btn.setText("源码")
            if self._current_markdown:
                self._preview.setPlainText(self._current_markdown)
        else:
            self._view_mode_btn.setText("预览")
            if self._current_markdown:
                self._render_markdown(self._current_markdown)

    def _render_markdown(self, text):
        try:
            import markdown as md_lib
            from pygments.formatters import HtmlFormatter
            extensions = ["fenced_code", "codehilite", "tables", "toc", "nl2br"]
            ext_configs = {"codehilite": {"css_class": "highlight", "use_pygments": True}}
            body_html = md_lib.markdown(text, extensions=extensions, extension_configs=ext_configs)
            pygments_css = HtmlFormatter().get_style_defs(".highlight")
        except ImportError:
            body_html = "<pre>" + html_mod.escape(text) + "</pre>"
            pygments_css = ""

        bg = self._theme.bg_color()
        fg = self._theme.text_color()
        border = self._theme.border_color()
        accent = self._theme.accent_color()

        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  {pygments_css}
  body {{
    background: {bg};
    color: {fg};
    font-family: "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    max-width: 900px;
    margin: 0 auto;
    padding: 10px 20px;
  }}
  h1, h2, h3, h4, h5, h6 {{ color: {fg}; margin-top: 20px; }}
  h1 {{ border-bottom: 1px solid {border}; padding-bottom: 6px; font-size: 22px; }}
  h2 {{ font-size: 18px; }}
  code {{
    background: {accent}20;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: "Consolas", "Courier New", monospace;
  }}
  pre {{
    background: {accent}08;
    border: 1px solid {border};
    border-radius: 8px;
    padding: 14px;
    overflow-x: auto;
  }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid {border}; padding: 8px 12px; text-align: left; }}
  th {{ background: {accent}10; }}
  blockquote {{
    border-left: 4px solid {accent};
    margin: 12px 0;
    padding: 6px 16px;
    background: {accent}08;
  }}
  img {{ max-width: 100%; }}
  a {{ color: {accent}; }}
</style></head><body>{body_html}</body></html>"""
        self._preview.setHtml(full_html)

    def _save_file(self, batch=False):
        if batch:
            if not self._conversion_results:
                QMessageBox.information(self, "提示", "没有可导出的文件。")
                return
            folder = QFileDialog.getExistingDirectory(self, "选择导出目标文件夹")
            if not folder:
                return
            success = 0
            for fp, md in self._conversion_results.items():
                name = os.path.splitext(os.path.basename(fp))[0] + ".md"
                out = os.path.join(folder, name)
                try:
                    with open(out, "w", encoding="utf-8") as f:
                        f.write(md)
                    success += 1
                except Exception:
                    pass
            self._status.setText(f"✅ 已导出 {success}/{len(self._conversion_results)} 个文件")
            return
        if not self._current_markdown:
            QMessageBox.information(self, "提示", "没有可保存的内容。")
            return
        ask = self._settings.ask_save_each_time
        default_dir = self._settings.default_save_path
        if ask or not default_dir:
            suggested = "output.md"
            if self._current_file:
                base = os.path.splitext(os.path.basename(self._current_file))[0]
                suggested = base + ".md"
            path, _ = QFileDialog.getSaveFileName(self, "保存 Markdown", suggested, "Markdown (*.md);;所有文件 (*)")
        else:
            base = os.path.splitext(os.path.basename(self._current_file or "output"))[0]
            path = os.path.join(default_dir, base + ".md")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._current_markdown)
                self._status.setText(f"已保存: {path}")
            except OSError as e:
                QMessageBox.critical(self, "保存失败", str(e))

    def _copy_to_clipboard(self):
        if not self._current_markdown:
            QMessageBox.information(self, "提示", "没有可复制的内容。")
            return
        QApplication.clipboard().setText(self._current_markdown)
        self._status.setText("已复制到剪贴板")

    def _clear_content(self):
        self._current_file = None
        self._current_markdown = ""
        self._file_list.clear()
        self._upload_panel.clear_queue()
        self._preview.clear()
        self._status.setText("已清空")

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self._theme, self)
        dlg.exec()
        self.history_mgr._max = self._settings.max_history

    def _clear_history(self):
        self.history_mgr.clear()
        self._refresh_history()

    def _refresh_history(self):
        self._hist_panel.list_widget.clear()
        for entry in self.history_mgr.entries:
            ts = time.strftime("%H:%M", time.localtime(entry.timestamp))
            preview = entry.output_preview[:50] if entry.output_preview else ''
            text = f"{entry.file_name}  |  {ts}  |  {preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry.file_path)
            item.setToolTip(entry.file_path)
            self._hist_panel.list_widget.addItem(item)
        self._hist_panel.set_count(len(self.history_mgr.entries))

    def _on_history_clicked(self, item):
        path = item.data(Qt.UserRole)
        if path and os.path.isfile(path):
            self._on_files_dropped([path])
            self._convert_file(path)

    @staticmethod
    def _format_size(size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


    def _show_about(self):
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

    def _check_update_background(self):
        from app.updater import check_latest_release as _cr, get_local_kernel_version as _kv
        try:
            _r = _cr()
            _k = _kv()
            if _r and _r.version > _k:
                self._status.setText(f"📦 新内核 v{_r.version} 可用（点击设置查看）")
        except Exception:
            pass

    def closeEvent(self, event):
        self._settings.window_geometry = self.saveGeometry()
        self._settings.window_splitter_outer = self._outer_splitter.saveState()
        self._settings.window_splitter_inner = self._inner_splitter.saveState()
        self._settings.sync()
        super().closeEvent(event)

