# SPDX-License-Identifier: MIT
"""MarkItDown converters backed by the optional local OCR component."""

from __future__ import annotations

import io
from typing import Any, BinaryIO

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo
from markitdown.converters._image_converter import ImageConverter
from markitdown.converters._pdf_converter import (
    PdfConverter,
    _extract_form_content_from_words,
)

from .ocr import OcrEngineClient, count_visible_characters


class LocalOcrImageConverter(DocumentConverter):
    _extensions = {".jpg", ".jpeg", ".png"}

    def __init__(self, engine: OcrEngineClient) -> None:
        self._engine = engine
        self._fallback = ImageConverter()

    def accepts(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> bool:
        return (stream_info.extension or "").lower() in self._extensions

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        base = self._fallback.convert(
            file_stream, stream_info, **kwargs
        ).markdown.strip()
        result = self._engine.recognise(stream_info.local_path or "", "image")
        text = "\n".join(
            page.get("markdown", "").strip() for page in result.get("pages", [])
        )
        sections = [
            section
            for section in (base, "## OCR 文本\n" + text.strip())
            if section.strip()
        ]
        return DocumentConverterResult(markdown="\n\n".join(sections))


class LocalOcrPdfConverter(DocumentConverter):
    _extension = ".pdf"

    def __init__(
        self,
        engine: OcrEngineClient,
        min_native_characters: int = 32,
        fallback_converter: DocumentConverter | None = None,
    ) -> None:
        self._engine = engine
        self._min_native_characters = min_native_characters
        self._fallback = fallback_converter or PdfConverter()

    def accepts(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> bool:
        return (stream_info.extension or "").lower() == self._extension

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        file_path = stream_info.local_path or ""
        if not file_path:
            raise ValueError("本地 OCR 仅支持本地 PDF 文件")
        pdf_data = file_stream.read()
        base = self._fallback.convert(
            io.BytesIO(pdf_data), stream_info, **kwargs
        ).markdown.strip()
        try:
            native_pages, has_form_content = self._extract_native_pages(pdf_data)
        except Exception:
            native_pages = self._blank_pages(pdf_data)
            has_form_content = False
        ocr_pages = [
            index
            for index, text in enumerate(native_pages, start=1)
            if count_visible_characters(text) < self._min_native_characters
        ]
        if not ocr_pages:
            return DocumentConverterResult(markdown=base)
        sections = [base] if base else []
        result = self._engine.recognise(file_path, "pdf", ocr_pages)
        recognised = {
            int(page["number"]): str(page.get("markdown", ""))
            for page in result.get("pages", [])
        }
        base_pages = self._base_pages(base, len(native_pages))
        merge_source = native_pages if has_form_content else base_pages
        merged = self._merge_pages(merge_source, recognised, ocr_pages)
        if merged:
            sections = [merged]
        else:
            ocr_sections = ["## OCR 文本"]
            for page_number in ocr_pages:
                text = recognised.get(page_number, "").strip()
                if text:
                    ocr_sections.append(f"### 第 {page_number} 页\n{text}")
            if len(ocr_sections) > 1:
                sections.append("\n\n".join(ocr_sections))
        return DocumentConverterResult(markdown="\n\n".join(sections))

    @staticmethod
    def _extract_native_pages(pdf_data: bytes) -> tuple[list[str], bool]:
        import pdfplumber

        pages: list[str] = []
        has_form_content = False
        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            for page in pdf.pages:
                try:
                    form_content = _extract_form_content_from_words(page)
                    if form_content is not None:
                        has_form_content = True
                        text = form_content
                    else:
                        text = page.extract_text() or ""
                    pages.append(text.strip())
                finally:
                    page.close()

        return pages, has_form_content

    @staticmethod
    def _blank_pages(pdf_data: bytes) -> list[str]:
        try:
            import fitz

            document = fitz.open(stream=pdf_data, filetype="pdf")
            try:
                return [""] * document.page_count
            finally:
                document.close()
        except Exception:
            return []

    @staticmethod
    def _base_pages(base: str, page_count: int) -> list[str]:
        if not base or page_count <= 0:
            return []
        pages = [part.strip() for part in base.split("\f")]
        if len(pages) == page_count:
            return pages
        return []

    @staticmethod
    def _merge_pages(
        native_pages: list[str], recognised: dict[int, str], ocr_pages: list[int]
    ) -> str:
        if not native_pages:
            return ""
        sections: list[str] = []
        ocr_header_added = False
        for page_number, native in enumerate(native_pages, start=1):
            if page_number in ocr_pages:
                text = recognised.get(page_number, "").strip()
                if text:
                    if not ocr_header_added:
                        sections.append("## OCR 文本")
                        ocr_header_added = True
                    sections.append(f"### 第 {page_number} 页\n{text}")
                    continue
            if native.strip():
                sections.append(native.strip())
        return "\n\n".join(sections)
