import os
import tempfile
import unittest
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QMimeData, QUrl, Qt, QPoint
from PySide6.QtGui import QDragEnterEvent

from app.float_window import FloatWindow, State
from app.dialogs import SettingsDialog
from app.history import HistoryManager
from app.main_window import MainWindow
from app.theme import ThemeManager, ThemePalette


class _Settings:
    max_file_mib = 200
    max_batch_items = 100
    max_pdf_pages = 500
    max_zip_mib = 1024
    window_geometry = None
    theme_mode = "light"
    show_float_window = False
    close_to_tray = False
    default_save_path = ""
    ask_save_each_time = True
    max_history = 50
    float_edge = None
    float_position = None
    collapse_delay = 100
    reduce_motion = True

    def sync(self):
        pass


class _History:
    def __init__(self):
        self.entries = []

    def add(self, entry):
        self.entries.insert(0, entry)

    def clear(self):
        self.entries.clear()

    def mark_export(self, *_args):
        pass

    def mark_pinned(self, *_args):
        file_path, pinned_path = _args
        for entry in self.entries:
            if entry.file_path == file_path:
                entry.pinned_path = pinned_path

    @property
    def pinned_entries(self):
        return [entry for entry in self.entries if entry.pinned_path]

    def unpin(self, file_path):
        for entry in self.entries:
            if entry.file_path == file_path:
                path = entry.pinned_path
                entry.pinned_path = ""
                if path:
                    Path(path).unlink(missing_ok=True)
                return path
        return ""

    def clear_pins(self):
        paths = [entry.pinned_path for entry in self.entries if entry.pinned_path]
        for entry in self.entries:
            entry.pinned_path = ""
        for path in paths:
            Path(path).unlink(missing_ok=True)
        return paths


class WorkspaceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = _Settings()
        self.theme = ThemeManager()
        self.theme.set_mode("light")
        self.history = _History()
        self.window = MainWindow(self.settings, self.theme, self.history)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.hide()
        self.window._jobs.store.cleanup()
        self.window.deleteLater()
        self.app.processEvents()

    def test_responsive_workspace_modes(self):
        self.window.resize(800, 600)
        self.app.processEvents()
        self.assertEqual("Stacked", self.window._workspace_mode.value)
        self.window.resize(1000, 700)
        self.app.processEvents()
        self.assertEqual("Compact", self.window._workspace_mode.value)
        self.window.resize(1200, 800)
        self.app.processEvents()
        self.assertEqual("Wide", self.window._workspace_mode.value)

    def test_large_result_does_not_block_preview(self):
        from app.jobs import JobItem

        content = "| Column A | Column B |\n| --- | --- |\n" + "| sample text | more text |\n" * 10000
        self.window._current_markdown = content
        start = time.perf_counter()
        self.window._show_markdown(JobItem("large.csv"), content)
        self.app.processEvents()
        elapsed = time.perf_counter() - start
        print(f"Large preview UI stall: {elapsed:.3f}s")
        self.assertLess(elapsed, 1.0, "Result preview blocks the UI thread")

    def test_large_preview_paging_preserves_complete_result(self):
        from app.jobs import JobItem

        content = "中文 abc 123\n" * 4000 + "最后一行"
        self.window._current_markdown = content
        self.window._show_markdown(JobItem("large.txt"), content)
        parts = [self.window._preview.toPlainText()]
        while self.window._preview_next.isEnabled():
            self.window._preview_next.click()
            parts.append(self.window._preview.toPlainText())
        self.assertEqual(content, "".join(parts))
        self.window._toggle_preview_mode()
        self.assertEqual(parts[-1], self.window._preview.toPlainText())
        self.window._copy_btn.click()
        self.assertEqual(content, QApplication.clipboard().text())
        self.window._show_markdown(JobItem("small.txt"), "small result")
        self.assertTrue(self.window._preview_pager.isHidden())
        self.assertEqual("small result", self.window._preview.toPlainText())

    def test_stacked_resize_reflows_splitter_after_layout_activation(self):
        self.window.resize(720, 900)
        self.app.processEvents()
        queue_size, detail_size = self.window._splitter.sizes()
        self.assertGreater(queue_size, detail_size)
        self.assertGreaterEqual(queue_size + detail_size, self.window._splitter.height() - 2)

    def test_wide_splitter_scales_with_available_width(self):
        self.window.resize(1600, 900)
        self.app.processEvents()
        self.window._splitter.setSizes([390, 560])
        self.window._apply_workspace_mode(self.window._workspace_mode)
        self.app.processEvents()
        total = self.window._splitter.width()
        queue_size, detail_size = self.window._splitter.sizes()
        self.assertGreaterEqual(queue_size, round(total * 0.28))
        self.assertGreater(detail_size, queue_size)
        self.assertGreaterEqual(queue_size + detail_size, total - 2)

    def test_horizontal_queue_is_limited_to_half_available_width(self):
        self.window.resize(1280, 800)
        self.app.processEvents()
        total = self.window._splitter.width()
        self.window._splitter.setSizes([total - 100, 100])
        self.window._on_splitter_moved(total - 100, 1)
        self.app.processEvents()
        queue_size, detail_size = self.window._splitter.sizes()
        self.assertLessEqual(queue_size, total // 2)
        self.assertGreater(detail_size, 0)

    def test_stacked_layout_does_not_squash_queue_controls(self):
        self.window.resize(800, 600)
        self.app.processEvents()
        self.assertEqual("Stacked", self.window._workspace_mode.value)
        self.assertTrue(self.window._job_list.isVisible())
        self.assertEqual(0, self.window._job_list.count())
        self.assertTrue(self.window._job_list.empty_label.isVisible())
        self.assertGreaterEqual(
            self.window._start_btn.height(), self.window._start_btn.sizeHint().height()
        )
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.txt"
            source.write_text("sample", encoding="utf-8")
            self.window._jobs.enqueue([str(source)])
            self.window._refresh_jobs()
            self.app.processEvents()
            self.assertTrue(self.window._job_list.isVisible())
            self.assertGreaterEqual(
                self.window._job_list.height(), self.window._job_list.minimumSizeHint().height()
            )

    def test_minimum_height_keeps_empty_queue_above_footer(self):
        self.window.resize(self.window.minimumWidth(), self.window.minimumHeight())
        self.app.processEvents()
        self.assertGreaterEqual(
            self.window._queue_scroll.viewport().height(),
            self.window._queue_content.minimumSizeHint().height() - 2,
        )
        list_bottom = self.window._job_list.geometry().bottom()
        viewport_bottom = self.window._queue_scroll.viewport().rect().bottom()
        self.assertGreaterEqual(self.window._job_list.height(), 100)
        self.assertLessEqual(viewport_bottom - list_bottom, 20)

    def test_low_height_keeps_queue_actions_in_sticky_footer(self):
        self.window.resize(720, 420)
        self.app.processEvents()
        self.assertEqual("Stacked", self.window._workspace_mode.value)
        self.assertTrue(self.window._queue_controls.isVisible())
        for button in (self.window._start_btn, self.window._cancel_btn, self.window._retry_btn):
            self.assertTrue(button.isVisible())
            bottom = button.mapTo(self.window._queue_pane, QPoint(0, button.height())).y()
            self.assertLessEqual(bottom, self.window._queue_pane.height())

    def test_narrow_header_does_not_clip_actions(self):
        self.window.resize(734, 622)
        self.app.processEvents()
        header = self.window.centralWidget().layout().itemAt(0).layout()
        self.assertGreaterEqual(header.geometry().width(), header.minimumSize().width())
        self.assertTrue(self.window._header_more_btn.isVisible())
        self.assertFalse(self.window._history_btn.isVisible())
        self.assertFalse(self.window._settings_btn.isVisible())
        self.window.resize(1000, 700)
        self.app.processEvents()
        self.assertTrue(self.window._header_more_btn.isVisible())
        self.assertFalse(self.window._history_btn.isVisible())
        self.assertFalse(self.window._settings_btn.isVisible())

    def test_history_button_toggles_history_dock(self):
        self.assertFalse(self.window._history_dock.isVisible())
        self.window._history_btn.click()
        self.app.processEvents()
        self.assertTrue(self.window._history_dock.isVisible())
        self.assertTrue(self.window._history_btn.isChecked())
        self.window._history_btn.click()
        self.app.processEvents()
        self.assertFalse(self.window._history_dock.isVisible())
        self.assertFalse(self.window._history_btn.isChecked())

    def test_stacked_header_moves_queue_toggle_into_more_menu(self):
        self.window.resize(720, 520)
        self.app.processEvents()
        self.assertFalse(self.window._queue_toggle_btn.isVisible())
        self.assertTrue(self.window._import_btn.isVisible())
        self.assertTrue(self.window._header_more_btn.isVisible())
        self.assertTrue(self.window._theme_btn.isVisible())

    def test_ocr_progress_uses_ocr_stage_label(self):
        self.window._on_convert_progress(
            {"phase": "ocr", "current": 1, "total": 2, "page": 1}
        )
        self.assertIn("OCR 识别", self.window._progress_meta.text())

    def test_keyboard_activation_selects_job(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.txt"
            source.write_text("sample", encoding="utf-8")
            self.window._jobs.enqueue([str(source)])
            self.window._refresh_jobs()
            activated = []
            self.window._job_list.item_activated.connect(activated.append)
            self.window._job_list.setFocus()
            QTest.keyClick(self.window._job_list, Qt.Key.Key_Return)
            self.assertEqual([str(source)], activated)
            self.assertEqual(str(source), self.window._current_file)

    def test_pin_action_toggles_to_single_unpin(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.txt"
            source.write_text("sample", encoding="utf-8")
            self.window._jobs.enqueue([str(source)])
            item = self.window._jobs.items[0]
            item.state = "success"
            item.result_path = self.window._jobs.store.write(str(source), "markdown")
            self.window._current_file = str(source)
            self.window.history_mgr.add(HistoryManager.make_entry(str(source)))
            self.window._pin_current_result()
            self.window._refresh_pin_actions()
            self.assertEqual("取消固定", self.window._pin_action.text())
            self.window._toggle_pin_current_result()
            self.assertEqual("固定结果", self.window._pin_action.text())
            self.assertIsNone(item.pinned_path)

    def test_float_window_keeps_drop_target_when_collapsed(self):
        float_window = FloatWindow(self.settings, self.theme)
        float_window.show()
        self.app.processEvents()
        float_window.set_state(State.ACTIVE)
        self.app.processEvents()
        self.assertGreaterEqual(float_window.width(), 200)
        float_window.set_state(State.COLLAPSED)
        self.assertTrue(float_window.acceptDrops())
        float_window.close()

    def test_float_window_drag_does_not_create_external_overlay(self):
        float_window = FloatWindow(self.settings, self.theme)
        float_window.show()
        self.app.processEvents()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("C:/sample.txt")])
        event = QDragEnterEvent(
            QPoint(2, 2),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        float_window.dragEnterEvent(event)
        self.app.processEvents()
        self.assertFalse(float_window._bubble.isVisible())
        self.assertEqual(Qt.AlignmentFlag.AlignCenter, float_window._summary_label.alignment())
        float_window.close()

    def test_settings_cancel_restores_theme_preview(self):
        dialog = SettingsDialog(self.settings, self.theme, None, self.window)
        dialog._dark_rb.setChecked(True)
        self.app.processEvents()
        self.assertEqual("dark", self.theme.current_theme)
        dialog.reject()
        self.assertEqual("light", self.theme.mode)

    def test_theme_text_tokens_meet_normal_text_contrast(self):
        def luminance(color):
            values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            values = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
            return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]

        def contrast(first, second):
            a, b = luminance(first), luminance(second)
            return (max(a, b) + 0.05) / (min(a, b) + 0.05)

        for dark in (False, True):
            palette = ThemePalette(dark)
            self.assertGreaterEqual(contrast(palette.secondary_text, palette.bg), 4.5)
            self.assertGreaterEqual(contrast(palette.brand_on, palette.brand_strong), 4.5)


if __name__ == "__main__":
    unittest.main()
