# SPDX-License-Identifier: MIT
"""Standalone PaddleOCR engine. Read one JSON request and emit JSONL events."""

from __future__ import annotations

import json
import os
import sys
import traceback
from io import BytesIO
from pathlib import Path


def configure_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def emit(event_type: str, request_id: str = "", **data) -> None:
    print(json.dumps({"type": event_type, "request_id": request_id, **data}, ensure_ascii=False), flush=True)


def error_code(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "INPUT_NOT_FOUND"
    if isinstance(exc, ValueError):
        return "UNSUPPORTED_FILE_TYPE"
    if isinstance(exc, ImportError):
        return "MODEL_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        return "OCR_TIMEOUT"
    return "ENGINE_RUNTIME_ERROR"


def ocr_image(ocr, image) -> str:
    if isinstance(image, bytes):
        from PIL import Image
        import numpy as np

        image = np.array(Image.open(BytesIO(image)).convert("RGB"))
    result = ocr.predict(image)
    lines: list[str] = []
    for item in result:
        payload = item.json if hasattr(item, "json") else item
        if isinstance(payload, str):
            payload = json.loads(payload)
        for text in payload.get("res", {}).get("rec_texts", []):
            if text:
                lines.append(str(text))
    return "\n".join(lines)


def handle(request: dict) -> None:
    engine_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    bundled_models = engine_dir / "models"
    if bundled_models.is_dir():
        # Keep all model files inside the optional component. This prevents a
        # frozen engine from downloading models into the user's profile.
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(bundled_models)
    request_id = str(request.get("request_id", ""))
    input_path = Path(request["input_path"])
    if not input_path.is_file():
        raise FileNotFoundError("输入文件不存在")
    file_type = request.get("file_type")
    if file_type not in {"image", "pdf"}:
        raise ValueError("不支持的 OCR 文件类型")
    from paddleocr import PaddleOCR

    # Paddle 3.3's oneDNN backend fails for the PP-OCRv6 CPU graph on some
    # Windows hosts. The standard CPU backend is slower but consistently works.
    ocr = PaddleOCR(lang="ch", enable_mkldnn=False)
    if file_type == "image":
        emit("progress", request_id, current=1, total=1)
        emit("result", request_id, pages=[{"number": 1, "markdown": ocr_image(ocr, str(input_path))}])
        return
    import fitz

    requested_pages = {int(page) for page in request.get("pages", [])}
    document = fitz.open(input_path)
    pages = sorted(requested_pages or set(range(1, len(document) + 1)))
    results = []
    for current, page_number in enumerate(pages, start=1):
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        results.append({"number": page_number, "markdown": ocr_image(ocr, pixmap.tobytes("png"))})
        emit("progress", request_id, current=current, total=len(pages), page=page_number)
    document.close()
    emit("result", request_id, pages=results)


def main() -> int:
    request_id = ""
    try:
        if "--health" in sys.argv:
            engine_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
            if not (engine_dir / "models" / "official_models").is_dir():
                raise RuntimeError("bundled models missing")
            import paddle
            import paddleocr
            if not paddle.__version__ or not paddleocr.__version__:
                raise RuntimeError("Paddle runtime unavailable")
            emit("health", status="ok", protocol_version=1)
            return 0
        request = json.loads(sys.stdin.readline())
        if not isinstance(request, dict):
            raise ValueError("请求必须是 JSON 对象")
        request_id = str(request.get("request_id", ""))
        handle(request)
        return 0
    except Exception as exc:
        emit(
            "error",
            request_id,
            code=error_code(exc),
            message=str(exc)[:500],
            detail=traceback.format_exc()[-4000:],
        )
        return 1


if __name__ == "__main__":
    configure_stdio()
    raise SystemExit(main())
