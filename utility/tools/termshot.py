#!/usr/bin/env python3
"""
termshot.py - render a captured terminal transcript (.log) into PNG screenshots
that look like a real Ubuntu gnome-terminal window.

Log format (plain text, the source of truth committed under logs/):
    #CWD <path>        -> sets the directory shown in the prompt (not displayed)
    $ <command>        -> rendered as a coloured shell prompt + the command
    <anything else>    -> rendered as command output, ANSI SGR colours honoured

Usage:
    python3 termshot.py transcripts/session-13/x.log screenshots/session-13/
    python3 termshot.py --all transcripts/session-13/ screenshots/session-13/
"""
import getpass
import os
import re
import socket
import sys
import unicodedata

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- appearance
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SIZE = 15
HERE = os.path.dirname(os.path.abspath(__file__))
# glyphs missing from the monospace font (box-drawing is fine, emoji are not)
# fall back to these, the same way gnome-terminal falls back via fontconfig
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    os.path.join(HERE, "fonts", "NotoEmoji.ttf"),
]

BG = (0x30, 0x0A, 0x24)          # Ubuntu terminal purple
FG = (0xEE, 0xEE, 0xEC)          # Tango "white" foreground

HEADER_BG = (0x38, 0x38, 0x38)
HEADER_LINE = (0x1F, 0x1F, 0x1F)
HEADER_FG = (0xDE, 0xDE, 0xDE)
BTN_BG = (0x4F, 0x4F, 0x4F)
BTN_FG = (0xEE, 0xEE, 0xEE)

HEADER_H = 38
PAD_X = 12
PAD_Y = 10

COLS = 140
ROWS = 72

# taken from the machine the transcript is rendered on, never typed in by hand
USER = getpass.getuser()
HOST = socket.gethostname()

# ------------------------------------------------------------- Tango palette
TANGO = {
    30: (0x2E, 0x34, 0x36), 31: (0xCC, 0x00, 0x00), 32: (0x4E, 0x9A, 0x06),
    33: (0xC4, 0xA0, 0x00), 34: (0x34, 0x65, 0xA4), 35: (0x75, 0x50, 0x7B),
    36: (0x06, 0x98, 0x9A), 37: (0xD3, 0xD7, 0xCF),
    90: (0x55, 0x57, 0x53), 91: (0xEF, 0x29, 0x29), 92: (0x8A, 0xE2, 0x34),
    93: (0xFC, 0xE9, 0x4F), 94: (0x72, 0x9F, 0xCF), 95: (0xAD, 0x7F, 0xA8),
    96: (0x34, 0xE2, 0xE2), 97: (0xEE, 0xEE, 0xEC),
}
PROMPT_GREEN = TANGO[92]   # bold green  user@host
PROMPT_BLUE = TANGO[94]    # bold blue   path


def xterm256(n):
    """Map an xterm-256 colour index to RGB."""
    if n < 8:
        return TANGO[30 + n]
    if n < 16:
        return TANGO[90 + (n - 8)]
    if n < 232:
        n -= 16
        lv = [0, 95, 135, 175, 215, 255]
        return (lv[n // 36], lv[(n // 6) % 6], lv[n % 6])
    g = 8 + (n - 232) * 10
    return (g, g, g)


# ------------------------------------------------------------- ANSI handling
CSI_RE = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")
OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
OTHER_ESC_RE = re.compile(r"\x1b[()][0-9A-B]|\x1b[=>]|\x1b[MDE78]")


class Style:
    __slots__ = ("fg", "bg", "bold")

    def __init__(self, fg=None, bg=None, bold=False):
        self.fg, self.bg, self.bold = fg, bg, bold

    def copy(self):
        return Style(self.fg, self.bg, self.bold)


def apply_sgr(style, params):
    """Mutate `style` according to one CSI ... m parameter list."""
    if not params:
        params = [0]
    i = 0
    while i < len(params):
        p = params[i]
        if p == 0:
            style.fg, style.bg, style.bold = None, None, False
        elif p == 1:
            style.bold = True
        elif p in (21, 22):
            style.bold = False
        elif 30 <= p <= 37:
            style.fg = TANGO[p + 60] if style.bold else TANGO[p]
        elif p == 39:
            style.fg = None
        elif 40 <= p <= 47:
            style.bg = TANGO[p - 10]
        elif p == 49:
            style.bg = None
        elif 90 <= p <= 97:
            style.fg = TANGO[p]
        elif 100 <= p <= 107:
            style.bg = TANGO[p - 10]
        elif p in (38, 48):
            target = "fg" if p == 38 else "bg"
            if i + 1 < len(params) and params[i + 1] == 5:
                setattr(style, target, xterm256(params[i + 2]))
                i += 2
            elif i + 1 < len(params) and params[i + 1] == 2:
                setattr(style, target, tuple(params[i + 2:i + 5]))
                i += 4
        i += 1
    # bold applied after a colour was already chosen -> brighten it
    if style.bold and style.fg is not None:
        for base, bright in ((30, 90), (31, 91), (32, 92), (33, 93),
                             (34, 94), (35, 95), (36, 96), (37, 97)):
            if style.fg == TANGO[base]:
                style.fg = TANGO[bright]
                break


WIDE_FILL = "\0"   # second half of a double-width character


def char_cells(ch, style):
    """Cells a terminal would use for one character: 0, 1 or 2."""
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):          # combining marks, ZWJ, VS16 ...
        return []
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return [(ch, style), (WIDE_FILL, style)]
    return [(ch, style)]


def cells_from_ansi(text, style):
    """Turn one physical line of ANSI text into a list of (char, Style) cells."""
    text = OSC_RE.sub("", text)
    text = OTHER_ESC_RE.sub("", text)
    # a carriage return rewrites the line: keep only what a terminal would show
    if "\r" in text:
        text = text.split("\r")[-1]
    cells = []
    pos = 0
    for m in CSI_RE.finditer(text):
        chunk = text[pos:m.start()]
        for ch in chunk.expandtabs(8):
            cells.extend(char_cells(ch, style.copy()))
        if m.group(2) == "m":
            params = [int(x) if x else 0 for x in m.group(1).split(";")]
            apply_sgr(style, params)
        pos = m.end()
    for ch in text[pos:].expandtabs(8):
        cells.extend(char_cells(ch, style.copy()))
    return cells


# ------------------------------------------------------------ log -> screen
def build_lines(logpath):
    """Read a .log and return a flat list of wrapped screen lines of cells."""
    with open(logpath, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    cwd = "~"
    style = Style()
    screen = []

    for line in raw.split("\n"):
        if line.startswith("#CWD "):
            cwd = line[5:].strip()
            continue
        if line.startswith("#TITLE "):
            continue

        if line.startswith("$ "):
            style = Style()          # a fresh command resets attributes
            cells = []
            for ch in USER + "@" + HOST:
                cells.append((ch, Style(PROMPT_GREEN, None, True)))
            cells.append((":", Style(FG, None, False)))
            for ch in cwd:
                cells.append((ch, Style(PROMPT_BLUE, None, True)))
            cells.append(("$", Style(FG, None, False)))
            cells.append((" ", Style(FG, None, False)))
            for ch in line[2:].expandtabs(8):
                cells.extend(char_cells(ch, Style(FG, None, False)))
        else:
            cells = cells_from_ansi(line, style)

        # wrap at COLS, exactly like a terminal of that width would
        if not cells:
            screen.append([])
        else:
            for i in range(0, len(cells), COLS):
                screen.append(cells[i:i + COLS])

    return screen, cwd


def read_title(logpath):
    with open(logpath, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#TITLE "):
                return line[7:].strip()
    return None


# ------------------------------------------------------------------ drawing
def rounded_top(draw, box, radius, fill):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y0 + 2 * radius), radius, fill=fill)
    draw.rectangle((x0, y0 + radius, x1, y1), fill=fill)


def draw_header(draw, width, title, font_bold):
    rounded_top(draw, (0, 0, width - 1, HEADER_H), 9, HEADER_BG)
    draw.line((0, HEADER_H, width, HEADER_H), fill=HEADER_LINE)

    tw = draw.textlength(title, font=font_bold)
    draw.text(((width - tw) / 2, (HEADER_H - FONT_SIZE) / 2 - 1),
              title, font=font_bold, fill=HEADER_FG)

    # Yaru-style circular window buttons on the right
    r, cy = 9, HEADER_H // 2
    for i, glyph in enumerate(("−", "□", "×")):
        cx = width - 24 - (2 - i) * 30
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BTN_BG)
        gw = draw.textlength(glyph, font=font_bold)
        draw.text((cx - gw / 2, cy - FONT_SIZE / 2 - 1),
                  glyph, font=font_bold, fill=BTN_FG)


class GlyphPicker:
    """Pick the first font that really has a glyph for a character."""

    def __init__(self, font_reg, font_bold):
        self.primary = {False: font_reg, True: font_bold}
        self.fallbacks = [ImageFont.truetype(f, FONT_SIZE)
                          for f in FALLBACK_FONTS if os.path.exists(f)]
        self.cache = {}

    @staticmethod
    def _has(font, ch):
        missing = font.getmask("\U0010FFFD")
        got = font.getmask(ch)
        return got.size != missing.size or bytes(got) != bytes(missing)

    def pick(self, ch, bold):
        key = (ch, bold)
        if key not in self.cache:
            font = self.primary[bold]
            if ord(ch) > 0x2000 and not self._has(font, ch):
                for fb in self.fallbacks:
                    if self._has(fb, ch):
                        font = fb
                        break
            self.cache[key] = font
        return self.cache[key]


def render_page(lines, title, out_png, font_reg, font_bold, cw, lh):
    # trim trailing blank rows so a short transcript does not get a huge void
    used = len(lines)
    while used and not lines[used - 1]:
        used -= 1
    rows = min(ROWS, max(used + 1, 4))

    width = PAD_X * 2 + cw * COLS
    height = HEADER_H + 1 + PAD_Y * 2 + lh * rows

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    draw_header(d, width, title, font_bold)

    picker = GlyphPicker(font_reg, font_bold)
    top = HEADER_H + 1 + PAD_Y
    for row, cells in enumerate(lines[:rows]):
        y = top + row * lh
        for col, (ch, st) in enumerate(cells):
            if (ch == " " and st.bg is None) or ch == WIDE_FILL:
                continue
            x = PAD_X + col * cw
            wide = col + 1 < len(cells) and cells[col + 1][0] == WIDE_FILL
            span = 2 if wide else 1
            if st.bg is not None:
                d.rectangle((x, y, x + cw * span - 1, y + lh - 1), fill=st.bg)
            if ch != " ":
                font = picker.pick(ch, st.bold)
                if font in (font_reg, font_bold):
                    d.text((x, y), ch, font=font, fill=st.fg or FG)
                else:   # centre a fallback glyph inside its 1 or 2 cells
                    gw = d.textlength(ch, font=font)
                    d.text((x + (cw * span - gw) / 2, y), ch, font=font,
                           fill=st.fg or FG)
    img.save(out_png)
    return out_png, width, height


def render_log(logpath, outdir):
    font_reg = ImageFont.truetype(FONT_REG, FONT_SIZE)
    font_bold = ImageFont.truetype(FONT_BOLD, FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    cw = int(round(probe.textlength("M" * 100, font=font_reg) / 100))
    lh = FONT_SIZE + 4

    screen, cwd = build_lines(logpath)
    base = os.path.splitext(os.path.basename(logpath))[0]
    title = read_title(logpath) or f"{USER}@{HOST}: {cwd}"

    pages = [screen[i:i + ROWS] for i in range(0, len(screen), ROWS)] or [[]]
    made = []
    for idx, page in enumerate(pages, 1):
        name = base if len(pages) == 1 else f"{base}_{idx}"
        ptitle = title if len(pages) == 1 else f"{title}  ({idx}/{len(pages)})"
        out = os.path.join(outdir, name + ".png")
        made.append(render_page(page, ptitle, out, font_reg, font_bold, cw, lh))
    return made


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--all":
        logdir, outdir = args[1], args[2]
        logs = sorted(f for f in os.listdir(logdir) if f.endswith(".log"))
        targets = [os.path.join(logdir, f) for f in logs]
    else:
        targets, outdir = [args[0]], args[1]

    os.makedirs(outdir, exist_ok=True)
    for t in targets:
        for out, w, h in render_log(t, outdir):
            print(f"{out}  {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
