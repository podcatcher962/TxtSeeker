# -*- coding: utf-8 -*-
"""生成 TxtSeeker.ico：深色圆角方块 + 文档 + 放大镜（兰兰偏好：灰底 + 橙色主色）"""
import os
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 深色圆角底 + 橙边
d.rounded_rectangle([10, 10, S - 10, S - 10], radius=58,
                    fill="#2b2b2b", outline="#ff8c1a", width=10)

# 文档（偏左上）
d.rounded_rectangle([62, 46, 176, 196], radius=12, fill="#e8e8e8")
d.polygon([(176, 46), (140, 82), (176, 82)], fill="#9a9a9a")   # 折角
d.line([176, 46, 140, 82], fill="#6a6a6a", width=3)
d.line([140, 82, 176, 82], fill="#6a6a6a", width=3)

# 文档上的文字行（橙色）
for i, y in enumerate(range(102, 176, 22)):
    w = 92 if i < 3 else 54
    d.rounded_rectangle([80, y, 80 + w, y + 10], radius=5, fill="#ff8c1a")

# 放大镜（右下，压在文档上）
cx, cy, r = 168, 178, 44
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(43, 43, 43, 210),
          outline="#3aa6ff", width=11)
d.line([cx + int(r * 0.70), cy + int(r * 0.70),
        cx + int(r * 1.28), cy + int(r * 1.28)], fill="#3aa6ff", width=14)
# 镜片里的高亮线（示意“搜到了”）
d.rounded_rectangle([cx - 24, cy - 10, cx + 24, cy - 1], radius=4, fill="#ff8c1a")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TxtSeeker.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)])
print("saved:", out, os.path.getsize(out), "bytes")
