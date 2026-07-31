import io
import sys
import types
import unittest
from unittest.mock import patch

from app.local_ocr import LocalOcrPdfConverter
from markitdown import StreamInfo


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_words(self, **kwargs):
        return []

    def extract_text(self):
        return self._text

    def close(self):
        pass


class _FakePdf:
    def __init__(self):
        self.pages = [_FakePage("这是原生文字页面，包含足够内容以确保不会被 OCR 重复处理，并且保留原有表格和文本提取结果。"), _FakePage("")]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def recognise(self, file_path, file_type, pages=None):
        self.calls.append((file_path, file_type, pages))
        return {"pages": [{"number": 2, "markdown": "扫描页识别结果"}]}


class LocalOcrPdfConverterTests(unittest.TestCase):
    def test_only_low_text_pages_are_sent_to_ocr(self):
        engine = _FakeEngine()
        converter = LocalOcrPdfConverter(engine)
        fake_module = types.SimpleNamespace(open=lambda _: _FakePdf())
        stream_info = StreamInfo(local_path="C:/scan.pdf", extension=".pdf")
        with patch.dict(sys.modules, {"pdfplumber": fake_module}):
            result = converter.convert(io.BytesIO(b"pdf"), stream_info)

        self.assertEqual([("C:/scan.pdf", "pdf", [2])], engine.calls)
        self.assertIn("原生文字页面", result.markdown)
        self.assertIn("扫描页识别结果", result.markdown)


if __name__ == "__main__":
    unittest.main()
