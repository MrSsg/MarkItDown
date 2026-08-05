"""Create deterministic local Chinese OCR fixtures for release verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


TEXT = "离线 OCR 中文测试 2026"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.is_file():
        raise RuntimeError("需要 Windows 微软雅黑字体来生成中文 OCR 测试夹具")
    image = Image.new("RGB", (1600, 520), "white")
    painter = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 92)
    painter.text((110, 180), TEXT, fill="#17233d", font=font)
    image.save(output / "ocr-chinese.jpg", quality=96)
    image.save(output / "ocr-scan.pdf", "PDF", resolution=150.0)


if __name__ == "__main__":
    main()
