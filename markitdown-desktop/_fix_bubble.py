import os
p = r"C:\Users\szlyh\Documents\MarkItDown\markitdown-desktop\app\float_window.py"
c = open(p, encoding="utf-8").read()

# Remove bubble from start of _draw_active
import re
c = re.sub(
    r"# Bubble tip when file drag active\n        if self\._file_drag_active:.*?painter\.drawText\(tx \+ 16, ty \+ 24, txt\)\n        ",
    "",
    c,
    flags=re.DOTALL,
)

# Add bubble at the end (before last drawText)
last = 'painter.drawText(0, h - 18, w, 14, Qt.AlignmentFlag.AlignCenter, "Drop files to convert")'
bubble = (
    '        # Bubble when file drag active\n'
    '        if self._file_drag_active:\n'
    '            txt = "\\U0001f4c4 \\u62d6\\u62fd\\u6587\\u4ef6\\u5230\\u6b64\\u5f00\\u59cb\\u8f6c\\u6362"\n'
    '            painter.setPen(Qt.NoPen)\n'
    '            painter.setBrush(QColor(0, 0, 0, 180))\n'
    '            fm = painter.fontMetrics()\n'
    '            tw = fm.horizontalAdvance(txt) + 32\n'
    '            th = 36\n'
    '            tx = (w - tw) // 2\n'
    '            ty = h - 50\n'
    '            dp = QPainterPath()\n'
    '            dp.addRoundedRect(tx, ty, tw, th, 10, 10)\n'
    '            painter.drawPath(dp)\n'
    '            painter.setPen(QColor(255, 255, 255))\n'
    '            painter.setFont(QFont("Segoe UI", 10))\n'
    '            painter.drawText(tx + 16, ty + 24, txt)\n'
)
c = c.replace(last, bubble + last)

open(p, "w", encoding="utf-8").write(c)
print("Bubble fixed")
