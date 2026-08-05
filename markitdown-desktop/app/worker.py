# SPDX-License-Identifier: MIT
import os as _os
import traceback
import uuid
from PySide6.QtCore import QObject, Signal, QThread

from .local_ocr import LocalOcrImageConverter, LocalOcrPdfConverter
from .ocr import OcrComponentError, OcrComponentManager, OcrEngineClient


class ConvertWorker(QObject):
    started = Signal(str, str)
    progress = Signal(object)
    finished = Signal(str, str)
    error = Signal(object, str)
    ocr_unavailable = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._ocr_engine = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.isRunning()

    def start_convert(
        self, file_path, enable_ocr=False, ocr_manager=None, request_id=None
    ):
        if self._thread is not None and self._thread.isRunning():
            return False
        engine_path = None
        if enable_ocr:
            info = (ocr_manager or OcrComponentManager()).status()
            if info.installed and info.path:
                engine_path = str(info.path)
            else:
                self.ocr_unavailable.emit(info.message or "OCR 组件未安装")
        if not engine_path:
            self.close_ocr_engine()
        elif (
            self._ocr_engine is None or str(self._ocr_engine.engine_path) != engine_path
        ):
            self.close_ocr_engine()
            self._ocr_engine = OcrEngineClient(engine_path)
        self._thread = _ConvertThread(
            file_path, self._ocr_engine, request_id or uuid.uuid4().hex
        )
        self._thread.finished.connect(self._relay_thread_result)
        self._thread.progress.connect(self.progress.emit)
        self.started.emit(file_path, _os.path.basename(file_path))
        self._thread.start()
        return True

    def stop_owned_ocr_process(self):
        """Only the optional child process may be stopped; never terminate Qt work."""
        if self._ocr_engine is not None:
            self._ocr_engine.stop()

    def close_ocr_engine(self):
        if self._ocr_engine is not None:
            self._ocr_engine.close()
            self._ocr_engine = None

    def _relay_thread_result(self):
        thread = self._thread
        self._thread = None
        if thread is None:
            return
        if thread.error_payload is not None:
            self.error.emit(thread.error_payload, thread.file_path)
        else:
            self.finished.emit(thread.markdown or "", thread.file_path)


class _ConvertThread(QThread):
    progress = Signal(object)

    def __init__(self, file_path, ocr_engine=None, request_id=None):
        super().__init__()
        self._file_path = file_path
        self._ocr_engine = ocr_engine
        self._request_id = request_id
        self.markdown = None
        self.error_payload = None

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
            if self._ocr_engine:

                def report(event):
                    if event.get("type") == "progress":
                        self.progress.emit(
                            {
                                "phase": "ocr",
                                "request_id": self._request_id,
                                "current": int(event.get("current", 0)),
                                "total": int(event.get("total", 0)),
                                "page": event.get("page"),
                            }
                        )

                self._ocr_engine.request_id = self._request_id
                self._ocr_engine.progress_callback = report
                md.register_converter(
                    LocalOcrImageConverter(self._ocr_engine), priority=-1.0
                )
                md.register_converter(
                    LocalOcrPdfConverter(self._ocr_engine), priority=-1.0
                )
            result = md.convert(self._file_path)
            content = result.text_content
            self.markdown = content
        except OcrComponentError as exc:
            self.error_payload = {
                "stage": "ocr",
                "code": exc.code,
                "message": str(exc),
                "detail": traceback.format_exc(),
            }
        except ImportError as exc:
            self.error_payload = {
                "stage": "conversion",
                "code": "DEPENDENCY_MISSING",
                "message": str(exc),
                "detail": traceback.format_exc(),
            }
        except Exception:
            self.error_payload = {
                "stage": "conversion",
                "code": "CONVERSION_FAILED",
                "message": "转换失败",
                "detail": traceback.format_exc(),
            }
