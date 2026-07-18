# SPDX-License-Identifier: MIT
import os as _os
import traceback
from PySide6.QtCore import QObject, Signal, QThread

class ConvertWorker(QObject):
    started = Signal(str, str)
    progress = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    def start_convert(self, file_path, enable_ocr=False):
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(3000):
                self._thread.terminate()
                self._thread.wait()
        self._thread = _ConvertThread(file_path, enable_ocr)
        self._thread.result_ready.connect(self.finished)
        self._thread.error_occurred.connect(self.error)
        self.started.emit(file_path, _os.path.basename(file_path))
        self._thread.start()

class _ConvertThread(QThread):
    result_ready = Signal(str, str)
    error_occurred = Signal(str, str)

    def __init__(self, file_path, enable_ocr=False):
        super().__init__()
        self._file_path = file_path
        self._enable_ocr = enable_ocr

    def run(self):
        try:
            import warnings
            warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")
            from markitdown import MarkItDown
            md = MarkItDown(enable_plugins=self._enable_ocr)
            result = md.convert(self._file_path)
            content = result.text_content
            self.result_ready.emit(content, self._file_path)
        except ImportError as e:
            self.error_occurred.emit(str(e), self._file_path)
        except Exception:
            tb = traceback.format_exc()
            msg = (tb.splitlines()[-1] if tb.splitlines() else str(tb))[:200]
            self.error_occurred.emit(msg, self._file_path)