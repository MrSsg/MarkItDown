# SPDX-License-Identifier: MIT
"""MarkItDown converters backed by the optional local OCR component."""

from __future__ import annotations

import io
from typing import Any, BinaryIO

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo
from markitdown.converters._image_converter import ImageConverter
from markitdown.converters._pdf_converter import _extract_form_content_from_words

from .ocr import OcrEngineClient, count_visible_characters


class LocalOcrImageConverter(DocumentConverter):
    _extensions = {".jpg", ".jpeg", ".png"}

    def __init__(self, engine: OcrEngineClient) -> None:
        self._engine = engine
        self._fallback = ImageConverter()

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return (stream_info.extension or "").lower() in self._extensions

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        base = self._fallback.convert(file_stream, stream_info, **kwargs).markdown.strip()
        result = self._engine.recognise(stream_info.local_path or "", "image")
        text = "\n".join(page.get("markdown", "").strip() for page in result.get("pages", []))
        sections = [section for section in (base, "## OCR 文本\n" + text.strip()) if section.strip()]
        return DocumentConverterResult(markdown="\n\n".join(sections))


class LocalOcrPdfConverter(DocumentConverter):
    _extension = ".pdf"

    def __init__(self, engine: OcrEngineClient, min_native_characters: int = 32) -> None:
        self._engine = engine
        self._min_native_characters = min_native_characters

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return (stream_info.extension or "").lower() == self._extension

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        import pdfplumber

        file_path = stream_info.local_path or ""
        if not file_path:
            raise ValueError("本地 OCR 仅支持本地 PDF 文件")
        chunks: list[str] = []
        ocr_pages: list[int] = []
        with pdfplumber.open(io.BytesIO(file_stream.read())) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = _extract_form_content_from_words(page) or (page.extract_text() or "")
                if count_visible_characters(text) < self._min_native_characters:
                    ocr_pages.append(index)
                    chunks.append("")
                else:
                    chunks.append(text.strip())
                page.close()
        if ocr_pages:
            result = self._engine.recognise(file_path, "pdf", ocr_pages)
            recognised = {int(page["number"]): page.get("markdown", "") for page in result.get("pages", [])}
            for page_number in ocr_pages:
                chunks[page_number - 1] = recognised.get(page_number, "")
        output = []
        for number, text in enumerate(chunks, start=1):
            if text.strip():
                output.append(f"<!-- page {number} -->\n{text.strip()}")
        return DocumentConverterResult(markdown="\n\n".join(output))
