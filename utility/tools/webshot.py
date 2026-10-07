#!/usr/bin/env python3
"""
webshot.py - screenshot a URL with headless Chrome and composite the result
into a browser window frame drawn with Pillow, so the screenshot itself shows
which URL / port the page was actually served from.

Usage:
    python3 webshot.py <url> <out.png> [tab-title] [width] [height] [wait-ms]
    python3 webshot.py http://localhost:9090/targets screenshots/session-20/targets.png "Prometheus"
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

# Chrome refuses to write into dot-directories under a snap confinement, so the
# raw capture is always staged in a plain directory.
STAGE = os.path.expanduser("~/shots")

UI_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
UI_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

TABSTRIP_BG = (0xDE, 0xE1, 0xE6)
TAB_BG = (0xFF, 0xFF, 0xFF)
TOOLBAR_BG = (0xFF, 0xFF, 0xFF)
URLBAR_BG = (0xF1, 0xF3, 0xF4)
TEXT = (0x3C, 0x40, 0x43)
MUTED = (0x5F, 0x63, 0x68)
BORDER = (0xC6, 0xC9, 0xCD)

TABSTRIP_H = 40
TOOLBAR_H = 48


def capture(url, width, height, wait_ms):
    os.makedirs(STAGE, exist_ok=True)
    fd, raw = tempfile.mkstemp(suffix=".png", dir=STAGE)
    os.close(fd)
    profile = tempfile.mkdtemp(dir=STAGE, prefix="prof_")
    cmd = [
        "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        "--ignore-certificate-errors",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={wait_ms}",
        f"--window-size={width},{height}",
        f"--screenshot={raw}", url,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return raw


def arrow(d, cx, cy, direction, colour):
    s = 5
    if direction == "left":
        d.line((cx + s, cy - s, cx - s, cy), fill=colour, width=2)
        d.line((cx - s, cy, cx + s, cy + s), fill=colour, width=2)
        d.line((cx - s, cy, cx + s + 2, cy), fill=colour, width=2)
    else:
        d.line((cx - s, cy - s, cx + s, cy), fill=colour, width=2)
        d.line((cx + s, cy, cx - s, cy + s), fill=colour, width=2)
        d.line((cx - s - 2, cy, cx + s, cy), fill=colour, width=2)


def frame(raw_png, out_png, url, tab_title):
    page = Image.open(raw_png).convert("RGB")
    pw, ph = page.size
    W = pw
    H = TABSTRIP_H + TOOLBAR_H + ph

    img = Image.new("RGB", (W, H), TABSTRIP_BG)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(UI_FONT, 13)
    fb = ImageFont.truetype(UI_BOLD, 13)

    # ---- tab strip with one active tab
    d.rectangle((0, 0, W, TABSTRIP_H), fill=TABSTRIP_BG)
    d.rounded_rectangle((8, 6, 268, TABSTRIP_H + 8), 8, fill=TAB_BG)
    d.ellipse((22, 16, 34, 28), fill=(0x1A, 0x73, 0xE8))
    title = tab_title if len(tab_title) <= 26 else tab_title[:25] + "…"
    d.text((44, 15), title, font=f, fill=TEXT)
    d.text((246, 14), "×", font=f, fill=MUTED)
    d.text((286, 13), "+", font=fb, fill=MUTED)

    # ---- toolbar
    ty = TABSTRIP_H
    d.rectangle((0, ty, W, ty + TOOLBAR_H), fill=TOOLBAR_BG)
    mid = ty + TOOLBAR_H // 2
    arrow(d, 24, mid, "left", MUTED)
    arrow(d, 56, mid, "right", (0xBD, 0xC1, 0xC6))
    d.arc((80, mid - 8, 96, mid + 8), 40, 330, fill=MUTED, width=2)
    d.polygon([(96, mid - 10), (96, mid - 1), (88, mid - 6)], fill=MUTED)

    # ---- url pill
    d.rounded_rectangle((116, mid - 15, W - 52, mid + 15), 15, fill=URLBAR_BG)
    d.rounded_rectangle((133, mid - 6, 141, mid + 5), 2, outline=MUTED, width=1)
    d.arc((133, mid - 11, 141, mid - 3), 180, 360, fill=MUTED, width=1)
    d.text((152, mid - 8), url, font=f, fill=TEXT)
    for i in range(3):                              # kebab menu
        d.ellipse((W - 32, mid - 8 + i * 6, W - 28, mid - 4 + i * 6), fill=MUTED)

    d.line((0, ty + TOOLBAR_H - 1, W, ty + TOOLBAR_H - 1), fill=BORDER)

    img.paste(page, (0, TABSTRIP_H + TOOLBAR_H))
    d.rectangle((0, 0, W - 1, H - 1), outline=BORDER)
    img.save(out_png)
    return out_png, W, H


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    url = sys.argv[1]
    out = sys.argv[2]
    tab = sys.argv[3] if len(sys.argv) > 3 else url
    width = int(sys.argv[4]) if len(sys.argv) > 4 else 1100
    height = int(sys.argv[5]) if len(sys.argv) > 5 else 620
    wait = int(sys.argv[6]) if len(sys.argv) > 6 else 4000

    raw = capture(url, width, height, wait)
    path, w, h = frame(raw, out, url, tab)
    os.unlink(raw)
    print(f"{path}  {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
