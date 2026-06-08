#!/usr/bin/env python
"""
Generate the brand image assets from a Captain Edward glyph.

The mark is the ornamental cross at glyph `plus.ss01` — the stylistic-set ('ss01')
alternate of '+' in Captain Edward (it still copy-pastes as '+'). Rendered straight from
the glyph outline (this Python has no HarfBuzz/raqm to apply the OT feature via text).

Run locally — the licensed font lives in the gitignored web/static/fonts/:
    python web/scripts/gen-brand-assets.py

Outputs (committed site assets — raster images of a glyph, i.e. a logo, NOT font data):
    web/static/favicon.ico, favicon.png, favicon-512.png, apple-touch-icon.png, og.png

Needs: Pillow, fontTools, brotli  (the system `python` has these).
"""
import os
import tempfile
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from PIL import Image, ImageDraw, ImageFont, ImageChops

WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(WEB, "static", "fonts")
OUT = os.path.join(WEB, "static")

PAPER = "#f7f2e9"
CREAM = "#fffdf8"
INK = "#262019"
TEAL = "#1f6f68"
MUTED = "#6f675a"
BORDER = "#e4dac6"
TEAL_T = (31, 111, 104, 255)
CREAM_T = (255, 253, 248, 255)

MARK = "plus.ss01"
WORDMARK = "Uncanny Atlas"
TAGLINE = "The visual tells people use to spot AI-generated images"
URL = "atlas.boat.horse"

_font = TTFont(os.path.join(FONTS, "CaptainEdward-Regular.woff2"))
_glyphs = _font.getGlyphSet()

# Captain Edward Regular as a TTF PIL can use (for the wordmark text only).
_tmp = tempfile.TemporaryDirectory()
_CE_TTF = os.path.join(_tmp.name, "CE.ttf")
_font.flavor = None
_font.save(_CE_TTF)


class _Flatten(BasePen):
    def __init__(self, gs, steps=48):
        super().__init__(gs)
        self.contours, self._cur, self.steps = [], None, steps

    def _moveTo(self, p):
        self._cur = [p]

    def _lineTo(self, p):
        self._cur.append(p)

    def _qCurveToOne(self, c, p):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps; mt = 1 - t
            self._cur.append((mt*mt*p0[0] + 2*mt*t*c[0] + t*t*p[0],
                              mt*mt*p0[1] + 2*mt*t*c[1] + t*t*p[1]))

    def _curveToOne(self, c1, c2, p):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps; mt = 1 - t
            self._cur.append((mt**3*p0[0] + 3*mt*mt*t*c1[0] + 3*mt*t*t*c2[0] + t**3*p[0],
                              mt**3*p0[1] + 3*mt*mt*t*c1[1] + 3*mt*t*t*c2[1] + t**3*p[1]))

    def _closePath(self):
        if self._cur:
            self.contours.append(self._cur); self._cur = None

    def _endPath(self):
        self._closePath()


def glyph_rgba(name, px, color, pad=0.14, ss=4):
    """RGBA image (px square) of one glyph in `color`, antialiased, centered, even-odd fill."""
    pen = _Flatten(_glyphs)
    _glyphs[name].draw(pen)
    cs = pen.contours
    xs = [x for c in cs for x, _ in c]
    ys = [y for c in cs for _, y in c]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    gw, gh = maxx - minx, maxy - miny
    S = px * ss
    sc = (S * (1 - 2 * pad)) / max(gw, gh)
    offx, offy = (S - gw * sc) / 2, (S - gh * sc) / 2
    acc = Image.new("1", (S, S), 0)
    for c in cs:
        pts = [((x - minx) * sc + offx, (maxy - y) * sc + offy) for x, y in c]
        m = Image.new("1", (S, S), 0)
        ImageDraw.Draw(m).polygon(pts, fill=1)
        acc = ImageChops.logical_xor(acc, m)
    mask = acc.convert("L").resize((px, px), Image.LANCZOS)
    return Image.composite(Image.new("RGBA", (px, px), color), Image.new("RGBA", (px, px), (0, 0, 0, 0)), mask)


def sans(px):
    for p in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, px)
    return ImageFont.load_default()


_m = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def fit(text, target_h):
    f = ImageFont.truetype(_CE_TTF, 200)
    l, t, r, b = _m.textbbox((0, 0), text, font=f)
    return ImageFont.truetype(_CE_TTF, max(1, int(200 * target_h / (b - t))))


def centered(draw, text, font, cx, cy, fill):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (r - l) / 2 - l, cy - (b - t) / 2 - t), text, font=font, fill=fill)


# --- favicon / app icon: cream mark on a teal rounded square ----------------
def make_icon(px, radius=0.22, pad=0.24):
    SS = 1024
    base = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle([0, 0, SS - 1, SS - 1], radius=int(SS * radius), fill=CREAM)
    base.alpha_composite(glyph_rgba(MARK, SS, TEAL_T, pad=pad))
    return base.resize((px, px), Image.LANCZOS)


make_icon(512).save(os.path.join(OUT, "favicon-512.png"))
make_icon(180).save(os.path.join(OUT, "apple-touch-icon.png"))
make_icon(32).save(os.path.join(OUT, "favicon.png"))
make_icon(256).save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])

# --- OG / Twitter card ------------------------------------------------------
W, H = 1200, 630
card = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(card)
d.rectangle([28, 28, W - 29, H - 29], outline=BORDER, width=2)
cx = W // 2

# Title line: "Uncanny Atlas" with the ornamental mark after it, centered as a group.
wm_font = fit(WORDMARK, 92)
wb = d.textbbox((0, 0), WORDMARK, font=wm_font)
wm_w, wm_h = wb[2] - wb[0], wb[3] - wb[1]
GBOX, GAP = 104, 26
glyph = glyph_rgba(MARK, GBOX, TEAL_T, pad=0.02)
x0 = (W - (wm_w + GAP + GBOX)) / 2
title_cy = 268
d.text((x0 - wb[0], title_cy - wm_h / 2 - wb[1]), WORDMARK, font=wm_font, fill=INK)
card.paste(glyph, (int(x0 + wm_w + GAP), int(title_cy - GBOX / 2)), glyph)

centered(d, TAGLINE, sans(34), cx, 398, MUTED)
centered(d, URL, sans(26), cx, 528, TEAL)
card.save(os.path.join(OUT, "og.png"))

print("wrote favicon.ico, favicon.png, favicon-512.png, apple-touch-icon.png, og.png  (mark = %s)" % MARK)
