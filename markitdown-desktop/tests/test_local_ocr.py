import io
import sys
import types
import unittest
from unittest.mock import patch

from app.local_ocr import LocalOcrPdfConverter
from markitdown import DocumentConverterResult, StreamInfo


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
        self.pages = [
            _FakePage("这是原生文字页面，包含足够内容以确保不会被 OCR 重复处理，并且保留原有表格和文本提取结果。"),
            _FakePage(""),
        ]

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


class _FakePdfConverter:
    def convert(self, *_args, **_kwargs):
        return DocumentConverterResult(markdown="原始表格结果\n| A | B |\n|---|---|")


class LocalOcrPdfConverterTests(unittest.TestCase):
    def test_only_low_text_pages_are_sent_to_ocr(self):
        engine = _FakeEngine()
        converter = LocalOcrPdfConverter(engine, fallback_converter=_FakePdfConverter())
        fake_module = types.SimpleNamespace(open=lambda _: _FakePdf())
        stream_info = StreamInfo(local_path="C:/scan.pdf", extension=".pdf")
        with patch.dict(sys.modules, {"pdfplumber": fake_module}):
            result = converter.convert(io.BytesIO(b"pdf"), stream_info)

        self.assertEqual([("C:/scan.pdf", "pdf", [2])], engine.calls)
        self.assertIn("原始表格结果", result.markdown)
        self.assertIn("| A | B |", result.markdown)
        self.assertIn("## OCR 文本", result.markdown)
        self.assertIn("扫描页识别结果", result.markdown)

    def test_ocr_page_is_kept_in_native_page_order(self):
        merged = LocalOcrPdfConverter._merge_pages(
            ["原生第一页", "", "原生第三页"],
            {2: "扫描第二页"},
            [2],
        )
        self.assertLess(merged.index("原生第一页"), merged.index("扫描第二页"))
        self.assertLess(merged.index("扫描第二页"), merged.index("原生第三页"))


if __name__ == "__main__":
    unittest.main()
