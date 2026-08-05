import tempfile
import unittest
import zipfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.jobs import JobController, JobFailure, JobState, ResourceLimits, SessionStore
from app.worker import ConvertWorker


ROOT = Path(__file__).resolve().parents[1]


class JobControllerTests(unittest.TestCase):
    def _controller(self, root: Path) -> JobController:
        return JobController(
            ResourceLimits(
                max_file_bytes=1024,
                max_batch_items=2,
                max_pdf_pages=500,
                max_zip_uncompressed_bytes=1024,
                max_zip_entries=10,
                max_zip_ratio=10,
            ),
            SessionStore(root / "sessions"),
        )

    def test_only_one_item_runs_and_cancel_skips_remaining_items(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            for name in ("one.txt", "two.txt"):
                path = root / name
                path.write_text(name, encoding="utf-8")
                paths.append(str(path))
            controller = self._controller(root)
            controller.enqueue(paths)
            current = controller.start()
            self.assertEqual("one.txt", current.file_name)
            controller.request_cancel()
            self.assertIsNone(controller.complete_current("done"))
            self.assertEqual(JobState.COMPLETED, controller.state)
            self.assertEqual("cancelled", controller.items[1].state)

    def test_timeout_discards_late_result_then_moves_to_next_item(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "one.txt", root / "two.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            controller = self._controller(root)
            controller.enqueue([str(first), str(second)])
            controller.start()
            controller.mark_timeout_waiting()
            next_item = controller.complete_current("late")
            self.assertEqual("CONVERSION_TIMEOUT", controller.items[0].failure.code)
            self.assertEqual("two.txt", next_item.file_name)
            self.assertEqual(JobState.RUNNING, controller.state)

    def test_preflight_limits_and_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            large = root / "large.txt"
            large.write_bytes(b"x" * 2048)
            controller = self._controller(root)
            controller.enqueue([str(large)])
            self.assertEqual("FILE_TOO_LARGE", controller.items[0].failure.code)
            controller.items[0].failure = JobFailure(
                "conversion", "FAILED", "temporary"
            )
            large.write_text("small", encoding="utf-8")
            self.assertEqual(1, len(controller.retry_failures()))

    def test_nested_zip_is_rejected_without_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "nested.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("inside.zip", b"not extracted")
            controller = self._controller(root)
            controller.enqueue([str(archive)])
            self.assertEqual("ZIP_NESTED_ARCHIVE", controller.items[0].failure.code)

    def test_session_store_is_disk_backed_and_cleanup_removes_result(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "sessions")
            result = store.write("C:/source.txt", "markdown")
            self.assertEqual("markdown", store.read(result))
            store.cleanup()
            self.assertFalse(result.exists())

    def test_pinned_result_survives_session_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "sessions")
            result = store.write("C:/source.txt", "markdown")
            pinned = store.pin(result, "source.txt")
            store.cleanup()
            self.assertEqual("markdown", pinned.read_text(encoding="utf-8"))

    def test_failures_are_written_to_session_log_with_request_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "broken.txt"
            source.write_text("broken", encoding="utf-8")
            controller = self._controller(root)
            controller.enqueue([str(source)])
            item = controller.start()
            self.assertIsNotNone(item)
            controller.fail_current(
                JobFailure("ocr", "INPUT_NOT_FOUND", "输入文件不存在", "detail")
            )
            logged = controller.store.read_log(controller.items[0].log_path)
            self.assertIn('"code": "INPUT_NOT_FOUND"', logged)
            self.assertIn(controller.items[0].request_id, logged)


class WorkerContractTests(unittest.TestCase):
    def test_worker_does_not_force_terminate_conversion_thread(self):
        source = (ROOT / "app" / "worker.py").read_text(encoding="utf-8")
        self.assertNotIn(".terminate(", source)
        self.assertIn("stop_owned_ocr_process", source)

    def test_worker_starts_next_job_after_previous_thread_finishes(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        del app
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.txt"
            second = Path(temp) / "second.txt"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            worker = ConvertWorker()
            loop = QEventLoop()
            results = []

            def on_finished(markdown, file_path):
                results.append((markdown, file_path))
                if len(results) == 1:
                    self.assertTrue(worker.start_convert(str(second)))
                else:
                    loop.quit()

            worker.finished.connect(on_finished)
            worker.error.connect(lambda _error, _path: loop.quit())
            self.assertTrue(worker.start_convert(str(first)))
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            self.assertEqual(2, len(results))
            self.assertFalse(worker.is_running)


if __name__ == "__main__":
    unittest.main()
