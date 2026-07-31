# SPDX-License-Identifier: MIT
import os as _os
import traceback
import uuid
from PySide6.QtCore import QObject, Signal, QThread

from .local_ocr import LocalOcrImageConverter, LocalOcrPdfConverter
from .ocr import OcrComponentManager, OcrEngineClient

class ConvertWorker(QObject):
    started = Signal(str, str)
    progress = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)
    ocr_unavailable = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.isRunning()

    def start_convert(self, file_path, enable_ocr=False, ocr_manager=None, request_id=None):
        if self._thread is not None and self._thread.isRunning():
            return False
        engine_path = None
        if enable_ocr:
            info = (ocr_manager or OcrComponentManager()).status()
            if info.installed and info.path:
                engine_path = str(info.path)
            else:
                self.ocr_unavailable.emit(info.message or "OCR 组件未安装")
        self._thread = _ConvertThread(file_path, engine_path, request_id or uuid.uuid4().hex)
        self._thread.finished.connect(self._relay_thread_result)
        self._thread.progress.connect(self.progress.emit)
        self.started.emit(file_path, _os.path.basename(file_path))
        self._thread.start()
        return True

    def stop_owned_ocr_process(self):
        """Only the optional child process may be stopped; never terminate Qt work."""
        if self._thread is not None:
            self._thread.stop_owned_ocr_process()

    def _relay_thread_result(self):
        thread = self._thread
        self._thread = None
        if thread is None:
            return
        if thread.error_message is not None:
            self.error.emit(thread.error_message, thread.file_path)
        else:
            self.finished.emit(thread.markdown or "", thread.file_path)

class _ConvertThread(QThread):
    progress = Signal(str)

    def __init__(self, file_path, engine_path=None, request_id=None):
        super().__init__()
        self._file_path = file_path
        self._engine_path = engine_path
        self._request_id = request_id
        self._ocr_engine = None
        self.markdown = None
        self.error_message = None

    @property
    def file_path(self):
        return self._file_path

    def stop_owned_ocr_process(self):
        if self._ocr_engine is not None:
            self._ocr_engine.stop()

    def run(self):
        try:
            import warnings
            warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")
            from markitdown import MarkItDown
            md = MarkItDown()
            if self._engine_path:
                def report(event):
                    if event.get("type") == "progress":
                        current = event.get("current", 0)
                        total = event.get("total", 0)
                        page = event.get("page")
                        suffix = f"，第 {page} 页" if page else ""
                        self.progress.emit(f"OCR 识别中 {current}/{total}{suffix}")
                engine = OcrEngineClient(
                    self._engine_path, request_id=self._request_id, progress_callback=report
                )
                self._ocr_engine = engine
                md.register_converter(LocalOcrImageConverter(engine), priority=-1.0)
                md.register_converter(LocalOcrPdfConverter(engine), priority=-1.0)
            result = md.convert(self._file_path)
            content = result.text_content
            self.markdown = content
        except ImportError as e:
            self.error_message = str(e)
        except Exception:
            self.error_message = traceback.format_exc()
