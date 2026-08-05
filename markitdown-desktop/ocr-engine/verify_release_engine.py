"""UTF-8 JSONL acceptance test for a frozen OCR engine release archive."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_engine(
    engine: Path, request: dict | None = None
) -> tuple[int, list[dict], str]:
    command = [str(engine)] + (["--health"] if request is None else [])
    completed = subprocess.run(
        command,
        input=None
        if request is None
        else json.dumps(request, ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    events: list[dict] = []
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return completed.returncode, events, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def request(path: Path, file_type: str, request_id: str) -> dict:
    return {
        "version": "1.0",
        "request_id": request_id,
        "input_path": str(path),
        "file_type": file_type,
        "pages": [],
        "language": "chinese_english",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--sample-image", required=True, type=Path)
    parser.add_argument("--fixture-dir", required=True, type=Path)
    args = parser.parse_args()
    require(args.engine.is_file(), "OCR 归档缺少 ocr-engine.exe")

    code, events, diagnostic = run_engine(args.engine)
    require(
        code == 0
        and any(
            event.get("type") == "health" and event.get("status") == "ok"
            for event in events
        ),
        f"OCR 健康检查失败: {diagnostic}",
    )

    for path, file_type, request_id, expected in (
        (args.sample_image, "image", "release-test", None),
        (args.fixture_dir / "ocr-chinese.jpg", "image", "chinese-image-test", "离线"),
        (args.fixture_dir / "ocr-scan.pdf", "pdf", "scan-pdf-test", "离线"),
    ):
        code, events, diagnostic = run_engine(
            args.engine, request(path, file_type, request_id)
        )
        result = next(
            (event for event in events if event.get("type") == "result"), None
        )
        text = "\n".join(
            str(page.get("markdown", "")) for page in (result or {}).get("pages", [])
        )
        require(
            code == 0 and result is not None and result.get("request_id") == request_id,
            f"OCR {file_type} 识别回归失败: events={events!r}; stderr={diagnostic}",
        )
        if expected:
            require(expected in text, f"OCR {file_type} 未识别预期中文文本: {text}")

    code, events, _ = run_engine(
        args.engine,
        request(args.fixture_dir / "missing.png", "image", "missing-file-test"),
    )
    error = next((event for event in events if event.get("type") == "error"), None)
    require(
        code == 1
        and error is not None
        and error.get("request_id") == "missing-file-test"
        and error.get("code") == "INPUT_NOT_FOUND",
        "OCR 错误协议回归失败",
    )
    print("OK: OCR 发布归档健康检查、中文图片、扫描 PDF 与错误协议")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    main()
