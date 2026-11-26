# -*- coding: utf-8 -*-
"""把网页用图压成 WebP：图 1400px / 人像 420px，显著减小首屏体积。

母版仍保留在 figures/ 与 data/raw/images/（用于 PDF 与再生成），docs/ 下只放 WebP。
"""
import sys, io
from pathlib import Path
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

def conv(src, dst, maxw, q):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if w > maxw:
        im = im.resize((maxw, round(h * maxw / w)), Image.LANCZOS)
    im.save(dst, "WEBP", quality=q, method=6)

before = after = 0
# 1) 分析图
for f in sorted((DOCS / "figures").glob("*.png")):
    b = f.stat().st_size
    dst = f.with_suffix(".webp")
    conv(f, dst, 1400, 84)
    a = dst.stat().st_size
    f.unlink()
    before += b; after += a
    print("fig  %-32s %6.0fKB -> %5.0fKB" % (f.name, b / 1024, a / 1024))

# 2) 人物像
for f in sorted((DOCS / "img").glob("*.jpg")):
    b = f.stat().st_size
    dst = f.with_suffix(".webp")
    conv(f, dst, 420, 82)
    a = dst.stat().st_size
    f.unlink()
    before += b; after += a

print("合计 %.1f MB -> %.1f MB（省 %.0f%%）" % (before / 1048576, after / 1048576,
                                            100 * (1 - after / max(before, 1))))
print("figures:", len(list((DOCS / "figures").glob("*.webp"))),
      " img:", len(list((DOCS / "img").glob("*.webp"))))
