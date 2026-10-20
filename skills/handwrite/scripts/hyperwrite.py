#!/usr/bin/env python3
"""
hyperwrite — raster handwriting synthesis with ink and paper physics.

The v1 engine (handwrite.py) draws glyph outlines into a vector PDF. That caps realism at
"nice handwriting font with jitter", because every `a` is the same outline and ink is a flat
fill. This engine rasterises instead, which buys the three things a vector page cannot have:

  1. GLYPH ALTERNATES   every occurrence of a letter is a *differently warped* letterform,
                        not the same outline rotated. This is the cue people cannot name.
  2. INK PHYSICS        pressure -> opacity, pooling where the pen slows, capillary bleed
                        into the fibres, ballpoint skip, paper grain visible THROUGH the ink.
  3. CAPTURE            the page is a photo or a scan of a document, not the document.

Everything is seeded: the same --seed is the same hand, page after page.
"""
import argparse, io, math, os, random, sys, json, zlib

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps
except ImportError:
    sys.exit("needs numpy + pillow:  python3 -m pip install numpy pillow")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_doc, hw_effects, hw_fonts, hw_options, hw_paper               # noqa: E402
from hw_ink import (Drift, Pen, bilinear_sample, draw_join, stroke_edges,  # noqa: E402,F401
                    value_noise_2d)
from hw_options import REALISM, build_parser, save_pages                  # noqa: E402

# ------------------------------------------------------------------ fonts
# The catalog, the per-script fallback and the fetch-on-use cache live in hw_fonts.
FONTS = hw_fonts.SYSTEM

def font_path(name):
    p = hw_fonts.resolve(name)
    if p:
        return p
    for k in ("caveat", "patrick", "bradley", "noteworthy"):
        p = hw_fonts.resolve(k)
        if p:
            sys.stderr.write(f"font {name!r} not found, falling back to {k}\n")
            return p
    sys.exit("no usable font on this machine")

# A hangul syllable or a kanji is written about 1.5 x-heights tall next to Latin writing.
BLOCK_REF = {"K": "가", "J": "あ", "Z": "中"}


def xheight_ratio(path, name=None):
    """x-height as a fraction of the em. Faces differ by 2x here, so every face is sized to
    match Caveat's x-height, which is what the engine's --size and presets were tuned on.
    A Korean, Japanese or Chinese hand is sized by its own script instead: its Latin x-height
    says nothing about how big its hangul or kana are, and NanumPen came out half size."""
    try:
        f = ImageFont.truetype(path, 200)
    except OSError:
        f = ImageFont.truetype(path, 200, index=0)
    cov = hw_fonts.coverage(path)
    scripts = hw_fonts.CATALOG.get(name, (None, None, "L"))[2]
    for s, ch in BLOCK_REF.items():
        if s in scripts and ord(ch) in cov:
            bb = f.getbbox(ch, anchor="ls")
            return max(0.2, (bb[3] - bb[1]) / 200.0 / 1.5)
    if ord("x") not in cov:
        return None
    bb = f.getbbox("x", anchor="ls")
    return max(0.2, -bb[1] / 200.0)

# ------------------------------------------------------------------ glyph variants
def stable_hash(s):
    return zlib.crc32(s.encode("utf-8"))

class GlyphBank:
    """Renders each character N times with a different low-frequency displacement field, so
    the third `e` on a line is a genuinely different shape from the first — the property a
    font can never have. handtextai rotates one outline by up to 2 degrees; this rewrites it."""
    def __init__(self, path, px, rng, variants=7, wobble=1.0, ss=3):
        self.px, self.ss, self.rng, self.variants = px, ss, rng, variants
        self.wobble = wobble
        try:
            self.font = ImageFont.truetype(path, int(px * ss))
        except OSError:
            self.font = ImageFont.truetype(path, int(px * ss), index=0)
        self.cache = {}
        self.pad = max(4, int(px * ss * 0.18))

    tighten = 1.0

    letter_space = 0.0

    def advance(self, ch):
        # a warped glyph is wider than its metric advance; pay for it here or
        # the letters collide and the page stops being readable
        w = self.font.getlength(ch, **self._dir(ch)) / self.ss * (1.0 + 0.055 * self.wobble)
        return w if ch == " " else w * self.tighten + self.letter_space * self.px

    @staticmethod
    def _dir(unit):
        # an Arabic or Hebrew word is one shaped unit; raqm needs to know it runs right to left
        return {"direction": "rtl"} if len(unit) > 1 and hw_fonts.is_rtl(unit) else {}

    def stroke_width(self):
        """The face's pen width in final px: the median run of ink across a row of `l` and `n`.
        Hand-drawn strokes (fraction bars, roots, table rules) must match it; a Caveat-sized
        nib on Reenie Beanie drew bars three times heavier than the letters (2026-09-24)."""
        runs = []
        for ch in "lnh":
            b = self._base(ch)
            if b is None:
                continue
            m = b[0] > 0.5
            for row in m[::2]:
                idx = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
                runs += list(idx[1::2] - idx[0::2])
        return float(np.median(runs)) / self.ss if runs else None

    def metrics(self, ch):
        """(advance, ascent, descent) in final px — what the maths layout needs."""
        bb = self.font.getbbox(ch, anchor="ls", **self._dir(ch))
        return self.advance(ch), max(0, -bb[1]) / self.ss, max(0, bb[3]) / self.ss

    def _base(self, ch):
        kw = self._dir(ch)
        bb = self.font.getbbox(ch, anchor="ls", **kw)
        w = bb[2] - bb[0]; h = bb[3] - bb[1]
        if w <= 0 or h <= 0:
            return None
        p = self.pad
        img = Image.new("L", (w + 2 * p, h + 2 * p), 0)
        ImageDraw.Draw(img).text((p - bb[0], p - bb[1]), ch, font=self.font,
                                 fill=255, anchor="ls", **kw)
        # origin of the glyph inside this raster, in supersampled pixels
        return np.asarray(img, np.float32) / 255.0, (p - bb[0]), (p - bb[1])

    def get(self, ch, variant):
        """Return (alpha HxW at final resolution, origin_x, origin_y_baseline)."""
        key = (ch, variant)
        if key in self.cache:
            return self.cache[key]
        base = self._base(ch)
        if base is None:
            self.cache[key] = None
            return None
        arr, ox, oy = base
        h, w = arr.shape
        # a smooth displacement field: the pen took a slightly different path this time
        amp = min(self.wobble, 2.0) * self.px * self.ss * 0.078
        # zlib.crc32, not hash(): str hashes are salted per process, so the same --seed drew a
        # different hand on every run and collision_rate swung 0.003-0.016 (2026-09-28)
        r = np.random.RandomState((stable_hash(ch) ^ (variant * 7919)) & 0x7FFFFFFF)
        dx = value_noise_2d(r, h, w, 3) * amp
        dy = value_noise_2d(r, h, w, 3) * amp
        # a shear on top of the warp: the wrist sat differently this time
        sh = (r.uniform(-1, 1) * 0.045 * min(self.wobble, 1.6))
        dx = dx + (np.mgrid[0:h, 0:w][0].astype(np.float32) - h * 0.5) * sh
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        arr = bilinear_sample(arr, xs + dx, ys + dy)
        # downsample: this is where the anti-aliased pen edge comes from
        im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "L")
        im = im.resize((max(1, w // self.ss), max(1, h // self.ss)), Image.LANCZOS)
        out = (np.asarray(im, np.float32) / 255.0, ox / self.ss, oy / self.ss)
        self.cache[key] = out
        return out

class MintedBank:
    """A GlyphBank backed by real letterforms minted from an image model.

    Same interface as GlyphBank, so the page renderer does not care which one it has. Any
    character the set does not cover falls through to the font — punctuation mostly, where
    nobody can tell a font full stop from a written one.
    """
    def __init__(self, setdir, px, rng, fallback, variants=14, wobble=1.0):
        self.px, self.rng, self.wobble = px, rng, wobble
        self.xh = px * 0.50                       # x-height, the unit the set is stored in
        self.fallback = fallback
        self.dir = setdir
        self.meta = json.load(open(os.path.join(setdir, "meta.json")))
        self.index = self.meta["glyphs"]
        self.bearing = self.xh * 0.17
        self.variants = max(variants, max((len(v) for v in self.index.values()), default=1))
        self.cache = {}

    def _rec(self, ch, variant):
        recs = self.index.get(ch)
        if not recs:
            return None
        return recs[variant % len(recs)]

    tighten = 1.0

    def advance(self, ch):
        if ch == " ":
            # never take this from the fallback font: its em is unrelated to the minted
            # set's x-height, which made word gaps swing wildly on the first minted page
            return self.xh * 0.62
        rec = self._rec(ch, 0)
        if rec is None:
            return self.fallback.advance(ch)
        return (rec["w_xh"] * self.xh + self.bearing) * self.tighten

    def metrics(self, ch):
        rec = self._rec(ch, 0)
        if rec is None:
            return self.fallback.metrics(ch)
        asc = rec["base_dy"] * self.xh
        return self.advance(ch), asc, max(0.0, rec["h_xh"] * self.xh - asc)

    def get(self, ch, variant):
        rec = self._rec(ch, variant)
        if rec is None:
            return self.fallback.get(ch, variant)
        key = (ch, variant)
        if key in self.cache:
            return self.cache[key]
        im = Image.open(os.path.join(self.dir, rec["file"])).convert("L")
        tw = max(1, int(round(rec["w_xh"] * self.xh)))
        th = max(1, int(round(rec["h_xh"] * self.xh)))
        im = im.resize((tw, th), Image.LANCZOS)
        arr = np.asarray(im, np.float32) / 255.0
        # the set holds at most a handful of real forms per letter; warp on top of them so a
        # long page does not repeat the same three shapes visibly
        if self.wobble > 0 and arr.size > 32:
            h, w = arr.shape
            r = np.random.RandomState((stable_hash(ch) ^ (variant * 7919) ^ 0x5eed) & 0x7FFFFFFF)
            # Matching the font path's amplitude (0.16) measurably raised the realism score and
            # visibly ATE THE LETTERS — at a small x-height it bit holes in the strokes and
            # `product` read as `produLt`. Readability first: the score is not the artefact.
            amp = min(self.wobble, 1.4) * self.xh * 0.075
            dx = value_noise_2d(r, h, w, 3) * amp
            dy = value_noise_2d(r, h, w, 3) * amp
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
            arr = bilinear_sample(arr, xs + dx, ys + dy)
        out = (np.clip(arr, 0, 1), 0.0, rec["base_dy"] * self.xh)
        self.cache[key] = out
        return out

# ------------------------------------------------------------------ layout
class Hand:
    """The statistical model of one person's hand. Seeded — reuse the seed across pages."""
    def __init__(self, rng, px, messiness=1.0, slant=0.0, sag=0.0, pressure=1.0,
                 drift=0.42, linestart=1.0):
        self.rng, self.px, self.m = rng, px, messiness
        self.slant_bias, self.sag, self.pressure = slant, sag, pressure
        self.linestart = linestart
        self.baseline = Drift(rng, scale=px * drift * messiness, step=px * 5.2)
        self.slantd   = Drift(rng, scale=2.6 * messiness,        step=px * 11.0)
        self.press    = Drift(rng, scale=0.46 * pressure,        step=px * 3.6)
        self.size_d   = Drift(rng, scale=0.028 * messiness,      step=px * 6.0)

    def fatigue(self, frac_down_page):
        """The hand tires. Jitter, slant spread and compression all grow toward the bottom."""
        return 1.0 + 0.55 * max(0.0, min(1.0, frac_down_page))

# ------------------------------------------------------------------ paper
# Paper specs, ruling and the hole punch live in hw_paper.
PAPERS = hw_paper.PAPERS
INKS = {
    # ballpoint and rollerball
    "blue":      (28, 44, 122), "darkblue":  (18, 28, 78),   "black":    (22, 22, 26),
    "blueblack": (24, 34, 66),  "red":       (140, 26, 30),  "green":    (26, 82, 54),
    # fountain pen and ink-bottle colours
    "royal":     (30, 58, 148), "teal":      (18, 92, 98),   "turquoise":(20, 118, 140),
    "purple":    (78, 38, 118), "plum":      (104, 34, 74),  "burgundy": (108, 26, 42),
    "sepia":     (92, 62, 36),  "brown":     (78, 52, 34),   "forest":   (22, 66, 42),
    "orange":    (168, 74, 20), "pink":      (176, 58, 104), "grey":     (86, 86, 92),
    # pencil and marker
    "pencil":    (74, 74, 80),  "pencil2b":  (58, 58, 64),   "marker":   (30, 30, 34),
}
# felt-tip highlighters, drawn UNDER the ink rather than over it
HIGHLIGHTERS = {
    "yellow": (252, 232, 96), "green": (168, 240, 150), "pink": (255, 168, 200),
    "orange": (255, 196, 110), "blue": (160, 214, 252),
}

def parse_ink(name):
    """A named ink, or any hex colour — `--ink "#4B2E83"` is a real request, not an edge case."""
    if isinstance(name, (tuple, list)):
        return tuple(name)
    n = str(name).strip()
    if n.startswith("#"):
        h = n[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            sys.exit(f"bad hex colour {name!r} — use #rgb or #rrggbb")
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            sys.exit(f"bad hex colour {name!r}")
    if n not in INKS:
        sys.exit(f"unknown ink {n!r} — one of {', '.join(sorted(INKS))}, or a #hex colour")
    return INKS[n]

def make_paper(rng, W, H, style, dpi, bg=None, texture=1.0, image=None):
    """Procedural paper. A JPEG texture tiles and repeats; noise does not, and it scales
    with DPI so a 600-dpi page has 600-dpi fibre rather than an upscaled photograph.
    `image` is a photographed sheet (--paper-image), already fitted: it carries its own fibre."""
    spec = dict(PAPERS[style])
    if image is not None:
        return image.copy(), spec
    if bg is not None:
        spec["bg"] = bg
    base = np.zeros((H, W, 3), np.float32)
    base[:] = np.array(spec["bg"], np.float32) / 255.0
    # fibre: two octaves, one visible at grain scale, one at blotch scale
    fibre = value_noise_2d(rng, H, W, max(6, W // 12), octaves=3) * 0.016 * texture
    blotch = value_noise_2d(rng, H, W, 5, octaves=2) * 0.013 * texture
    base *= (1.0 + fibre + blotch)[..., None]
    return base, spec

# ------------------------------------------------------------------ ink physics
def ink_physics(alpha, rng, dpi, bleed=1.0, pool=1.0, skip=0.35):
    """Turn a clean glyph mask into ink that a pen actually laid down.

    bleed  capillary spread into the fibres — a soft, low-opacity halo hugging every stroke
    pool   ink gathers where the nib slowed: stroke ends, tight turns, crossings. Approximated
           by eroding the mask; what survives is the thick part, which is where ink sits.
    skip   ballpoints skip. Tiny horizontal slivers of missing ink, rare, never on every letter.
    """
    a = alpha
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")
    r = max(1.0, dpi / 200.0)
    if bleed > 0:
        halo = np.asarray(im.filter(ImageFilter.GaussianBlur(0.9 * r)), np.float32) / 255.0
        a = np.maximum(a, halo * 0.30 * bleed)
    if pool > 0:
        core = np.asarray(im.filter(ImageFilter.MinFilter(3)), np.float32) / 255.0
        core = np.asarray(Image.fromarray((core * 255).astype(np.uint8), "L")
                          .filter(ImageFilter.GaussianBlur(0.5 * r)), np.float32) / 255.0
        # pool only where the stroke is ALREADY thick — filling every core turns the
        # whole page into a flat fill, which is the exact tell we are trying to remove
        blob = value_noise_2d(rng, *a.shape, max(6, a.shape[1] // 40), octaves=2)
        a = np.clip(a + core * (0.10 + 0.20 * np.clip(blob, 0, 1)) * pool, 0, 1.25)
    if skip > 0:
        h, w = a.shape
        streak = value_noise_2d(rng, h, w, max(4, w // 3), octaves=2)
        streak = np.asarray(Image.fromarray(((streak + 1) * 127).astype(np.uint8), "L")
                            .filter(ImageFilter.GaussianBlur(0.4 * r)), np.float32) / 255.0
        gap = (streak > (1.0 - 0.055 * skip)).astype(np.float32)
        a = a * (1.0 - gap * 0.85)
    return np.clip(a, 0, 1.25)

def composite(paper, alpha, ink_rgb, grain=0.22):
    """Ink TINTS the paper rather than covering it, so the fibre stays visible through the
    stroke. Covering the paper with a flat fill is the single most common tell in fake scans."""
    a = np.clip(alpha, 0, 1)[..., None]
    ink = np.array(ink_rgb, np.float32) / 255.0
    # multiply toward the ink colour, modulated by the paper's own luminance
    lum = paper.mean(axis=2, keepdims=True)
    tinted = ink * (1.0 - grain + grain * (lum / max(lum.mean(), 1e-6)))
    return paper * (1 - a) + np.clip(tinted, 0, 1) * a

def hl_band(alpha, rng, xh):
    """A highlighter is a wide wet felt tip: it covers the line, overshoots its ends, and
    wanders above and below the text rather than boxing it exactly."""
    im = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), "L")
    band = np.asarray(im.filter(ImageFilter.MaxFilter(3))
                        .filter(ImageFilter.GaussianBlur(xh * 0.55)), np.float32) / 255.0
    band = np.clip(band * 6.0, 0, 1)
    wob = value_noise_2d(rng, *band.shape, max(4, band.shape[1] // 90), octaves=2)
    return np.clip(band * (0.62 + 0.30 * np.clip(wob + 1, 0, 2)), 0, 0.85)

def heel_smudge(img, alpha, rng, amount, xh):
    """The heel of the writing hand drags across ink that is still wet. It shows up trailing
    to the right of a stroke and fading, and it is one of the few marks nothing but a hand
    leaves on a page."""
    im = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), "L")
    sm = np.asarray(im.filter(ImageFilter.GaussianBlur(xh * 0.30)), np.float32) / 255.0
    sh = int(max(1, xh * 0.5))
    trail = np.zeros_like(sm)
    trail[:, sh:] = sm[:, :-sh]
    patch = np.clip(value_noise_2d(rng, *sm.shape, 7, octaves=2), 0, 1)
    return img * (1.0 - (trail * patch * 0.07 * amount)[..., None])

# ------------------------------------------------------------------ capture
def apply_capture(img, rng, nrng, mode, dpi):
    """The artefact is not the page, it is a picture of the page. Skipping this step is why
    most 'handwritten' PDFs look like what they are: a render."""
    if mode == "print":
        return img
    H, W, _ = img.shape
    if mode in ("scan", "photo"):
        shade = value_noise_2d(nrng, H, W, 3, octaves=2)
        img = img * (1.0 + shade * (0.05 if mode == "scan" else 0.13))[..., None]
    if mode == "photo":
        # lighting falls off from one corner; phone flash or a window
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        cx, cy = rng.uniform(0.15, 0.85) * W, rng.uniform(0.05, 0.4) * H
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / math.hypot(W, H)
        img = img * (1.12 - 0.34 * d)[..., None]
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if mode == "photo":
        # keystone: the phone was not parallel to the desk
        k = rng.uniform(0.004, 0.012)
        # Image.QUAD wants the SOURCE quad as upper-left, LOWER-left, lower-right,
        # upper-right. Any other order transposes the page — it looks like a 90-degree
        # rotation and it is very easy to mistake for a layout bug.
        ul = (W * k,             H * k * 0.6)
        ll = (W * k * 0.5,       H * (1 - k * 0.15))
        lr = (W * (1 - k * 0.2), H)
        ur = (W * (1 - k * 0.4), 0)
        pil = pil.transform((W, H), Image.QUAD,
                            [c for pt in (ul, ll, lr, ur) for c in pt], Image.BICUBIC)
        pil = pil.filter(ImageFilter.GaussianBlur(0.35 * max(1, dpi / 200)))
    else:
        pil = pil.rotate(rng.uniform(-0.45, 0.45), Image.BICUBIC,
                         fillcolor=(252, 251, 248))
    arr = np.asarray(pil, np.float32) / 255.0
    n = nrng.normal(0, 0.010 if mode == "scan" else 0.018, arr.shape).astype(np.float32)
    arr = np.clip(arr + n, 0, 1)
    if mode == "scan":                                    # dust and specks on the glass
        for _ in range(int(rng.uniform(6, 22))):
            x, y = int(rng.uniform(0, W)), int(rng.uniform(0, H))
            s = int(rng.uniform(1, 3))
            arr[y:y + s, x:x + s] *= rng.uniform(0.4, 0.8)
    return arr

# ------------------------------------------------------------------ page render
def render_page(items, bank, hand, rng, nrng, cfg, prev_ink=None, bank_at=None, page_no=0):
    W, H, dpi = cfg["W"], cfg["H"], cfg["dpi"]
    paper, spec = make_paper(nrng, W, H, cfg["paper"], dpi, cfg.get("paper_rgb"), cfg["texture"],
                             cfg.get("paper_img"))
    if cfg.get("rule_rgb") and spec.get("rule"):
        spec["rule"] = cfg["rule_rgb"]
    if cfg.get("margin_line") is False:
        spec["guides"], spec["margin_rule"] = [], False
    gap = cfg["line_gap"]
    left, right = cfg["left"], cfg["right"]
    dx = 0
    if cfg.get("mirror") and page_no % 2 == 1:
        # the back of the sheet: margins and margin lines swap sides, the writing moves over
        dx = int((W - cfg["right"]) - cfg["left"])
        spec["guides"] = [("right" if s == "left" else "left", o, c, w)
                          for s, o, c, w in spec.get("guides", [])]
    hw_paper.draw_ruling(paper, rng, spec, dpi, gap / spec.get("write_every", 1),
                         cfg["rule_top"], left + dx)
    if cfg.get("holes"):
        hw_paper.punch_holes(paper, dpi)

    if prev_ink is not None and cfg["showthrough"] > 0:
        # Ink that soaks through paper spreads a long way and arrives as a smudge, not as
        # text. A blur of dpi/150 is about one pixel, which left page one's writing MIRRORED
        # AND READABLE on the back of page two — measured 2026-09-21. The spread has to scale
        # with the writing, not with the resolution: half an x-height is roughly right.
        xh = cfg["line_gap"] * 0.30
        st = np.asarray(Image.fromarray((np.clip(prev_ink, 0, 1) * 255).astype(np.uint8), "L")
                        .transpose(Image.FLIP_LEFT_RIGHT)
                        .filter(ImageFilter.GaussianBlur(max(1.5, xh * 0.55))), np.float32) / 255.0
        st = np.clip(st * 2.2, 0, 1) ** 1.6          # keep the darkest cores, drop the rest
        paper = composite(paper, st * 0.055 * cfg["showthrough"], cfg["ink_rgb"], grain=0.0)

    gnrng = np.random.RandomState(nrng.randint(1 << 30))
    pen = Pen(bank, hand, rng, gnrng, cfg, W, H, bank_at or (lambda s: (bank, s)))
    geo = dict(gap=gap, left=left, right=right)
    y0 = cfg["top"]
    main_ink = pen.alpha
    for it, row in items:
        y = y0 + row * gap * (1.0 + rng.gauss(0, 0.010 * hand.m))
        pen.at_row(y)
        pen.alpha = pen.alpha_fix if getattr(it, "ink", "main") == "correction" else main_ink
        hw_doc.draw_item(pen, it, y, geo)
    pen.alpha = main_ink
    if dx:
        for layer in (pen.alpha, pen.alpha_fix, pen.alpha_hl):
            layer[:] = np.roll(layer, dx, axis=1)
            if dx > 0:
                layer[:, :dx] = 0
            else:
                layer[:, dx:] = 0
        pen.pastes = [(p, x + dx, y, w, h) for p, x, y, w, h in pen.pastes]

    for path, x, y, w, h in pen.pastes:
        # an image stuck onto the page sits UNDER the ink, like a printed figure written around
        im = Image.open(path).convert("RGB").resize((max(1, w), max(1, h)), Image.LANCZOS)
        arr = np.asarray(im, np.float32) / 255.0
        y1, x1 = min(H, y + h), min(W, x + w)
        if y1 > y and x1 > x:
            paper[y:y1, x:x1] = paper[y:y1, x:x1] * arr[:y1 - y, :x1 - x]

    alpha = pen.alpha
    if cfg["ink_flow"] > 0:
        # the pen runs dry and floods again along the writing: slow, page-scale, never per letter
        flow = value_noise_2d(nrng, H, W, 4, octaves=2)
        alpha = alpha * np.clip(1.0 + flow * 0.33 * cfg["ink_flow"], 0.35, 1.3)
    alpha = ink_physics(alpha, nrng, dpi, cfg["bleed"], cfg["pool"], cfg["skip"])
    img = paper
    hl = pen.alpha_hl
    if cfg["highlight"]:
        hl = np.maximum(hl, hl_band(alpha, nrng, pen.xh))
    if hl.max() > 0:
        hl = np.asarray(Image.fromarray((hl * 255).astype(np.uint8), "L")
                        .filter(ImageFilter.GaussianBlur(pen.xh * 0.12)), np.float32) / 255.0
        img = composite(img, hl, HIGHLIGHTERS[cfg["highlight"] or "yellow"], grain=0.0)
    img = composite(img, alpha, cfg["ink_rgb"], grain=cfg["grain"])
    if pen.alpha_fix.max() > 0:
        fix = ink_physics(pen.alpha_fix, nrng, dpi, cfg["bleed"], cfg["pool"], 0.0)
        img = composite(img, fix, cfg["fix_rgb"], grain=cfg["grain"])
    if cfg["smudge"] > 0:
        img = heel_smudge(img, alpha, nrng, cfg["smudge"], pen.xh)
    if cfg["shading"] > 0:
        # a sheet is never lit evenly: a broad gradient plus a soft darker corner
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        ang = rng.uniform(0, 2 * math.pi)
        g = ((xx / W - 0.5) * math.cos(ang) + (yy / H - 0.5) * math.sin(ang))
        img = img * (1.0 - cfg["shading"] * 0.16 * (g + 0.5))[..., None]
    erng = hw_effects.effect_rng(cfg["seed"], page_no)
    img = hw_effects.shadow(img, erng, cfg["shadow"], cfg["effect"])
    img = apply_capture(img, rng, nrng, cfg["capture"], dpi)
    if cfg["blur"] > 0:
        pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        img = np.asarray(pil.filter(ImageFilter.GaussianBlur(cfg["blur"] * dpi / 200.0)),
                         np.float32) / 255.0
    img = hw_effects.contrast(img, cfg["contrast"])
    rate = pen.collisions / pen.pairs if pen.pairs else 0.0
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), alpha, rate

# ------------------------------------------------------------------ driver
PAGE_MM = hw_paper.PAGE_MM

def load_paper_image(path, W, H):
    """A photographed or scanned sheet as the paper, scaled to cover the page and centred, the
    way a sheet fills a scanner bed. text-to-handwriting tiles the file at its own size instead,
    which repeats a small image visibly across an A4 page."""
    p = os.path.expanduser(path)
    if not os.path.isfile(p):                  # a pipe or a device would hang the open
        sys.exit(f"--paper-image {path!r} is not a readable image: no such file")
    try:
        im = Image.open(p)
        im.load()
        im = ImageOps.exif_transpose(im)       # a phone photo is stored sideways plus a tag
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        sys.exit(f"--paper-image {path!r} is not a readable image: {e}")
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        # transparent areas are blank paper, not black
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)),
                                   im.convert("RGBA"))
    im = im.convert("RGB")
    k = max(W / im.width, H / im.height)
    im = im.resize((max(W, round(im.width * k)), max(H, round(im.height * k))), Image.LANCZOS)
    x0, y0 = (im.width - W) // 2, (im.height - H) // 2
    return np.asarray(im.crop((x0, y0, x0 + W, y0 + H)), np.float32) / 255.0

def build_bank_factory(a, em, nrng, text):
    """bank_at(scale) -> (bank, residual scale). Headings and maths are written at other sizes;
    rendering them from a bank at that size keeps the pen edge sharp instead of upscaling."""
    names = hw_fonts.fallback_chain(a.font, text) if a.fallback else [a.font]
    ref = xheight_ratio(font_path("caveat")) or 0.5
    paths = []
    for i, n in enumerate(names):
        p = font_path(n) if i == 0 else hw_fonts.resolve(n)
        if p and p not in [q for q, _ in paths]:
            paths.append((p, xheight_ratio(p, n) or ref))
    # Word gaps come from Caveat's proportions whatever the face: Reenie Beanie's own space is a
    # full x-height wide and its pages read as a row of separate words (2026-09-24).
    cav = ImageFont.truetype(font_path("caveat"), 200)
    space_ratio = cav.getlength(" ") / 200.0 * (1.0 + 0.055 * a.wobble)
    minted = None
    if a.glyphset:
        d = a.glyphset if os.path.isdir(a.glyphset) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "glyphsets", a.glyphset)
        if not os.path.exists(os.path.join(d, "meta.json")):
            sys.exit(f"no glyph set at {d} — run: glyphmint.py list")
        minted = d
    cache = {}

    def make(key):
        banks = []
        for p, r in paths:
            b = GlyphBank(p, em * key * ref / r, nrng, variants=max(1, a.variants),
                          wobble=a.wobble, ss=3)
            banks.append((b, hw_fonts.coverage(p)))
        if minted:
            mb = MintedBank(minted, em * key, nrng, banks[0][0], variants=max(1, a.variants),
                            wobble=a.wobble)
            banks[0] = (mb, banks[0][1] | {ord(c) for c in mb.index if len(c) == 1})
        stack = hw_fonts.FontStack(banks, px=em * key)
        if not minted:
            stack.space = em * key * space_ratio
            stack.stroke_px = banks[0][0].stroke_width()
        if a.cursive:
            # a joined hand sets its letters closer than a printed one, because the join
            # occupies the space the sidebearing would otherwise hold
            stack.tighten = 1.0 - 0.07 * min(a.cursive, 1.6)
        stack.letter_space = a.letter_spacing
        return stack

    def bank_at(scale):
        key = max(0.3, round(scale * 10) / 10)
        if key not in cache:
            cache[key] = make(key)
        return cache[key], scale / key
    return bank_at


def geometry(a, W, H, px_per_mm, xh):
    """Margins, row pitch and the first baseline, in px. Returns (geo dict, x-height)."""
    spec = PAPERS[a.paper]
    em = xh / 0.50                                # Caveat-ish x-height ratio
    ruling = spec.get("mm")
    if ruling:
        # On ruled paper the line spacing IS the ruling. Writing bigger does not move the
        # printed lines; it just fills more of the gap — and past a point it cannot.
        # `write_every` separates the PRINTED pitch from the WRITING pitch. On 5mm dot grid
        # or graph paper nobody writes on every row; they write across two squares. Treating
        # the printed pitch as the line spacing made 5mm papers physically unwritable.
        gap = ruling * px_per_mm * spec.get("write_every", 1)
        # An x-height of 4.6mm on a 5mm dot grid is not a small hand, it is an IMPOSSIBLE
        # one: the ascenders of one line land inside the descenders of the line above and
        # the page becomes unreadable. Measured 2026-09-21 on a moleskine render that got
        # shipped. Warning about it was not enough; it has to be prevented.
        max_xh = gap * 0.50
        if xh > max_xh and a.fit:
            shrunk = max_xh / px_per_mm
            sys.stderr.write(
                f"  fitted: x-height {a.size}mm does not fit {ruling}mm {a.paper} rule — "
                f"writing at {shrunk:.1f}mm. Pass --no-fit to override, or use wider paper.\n")
            xh = max_xh
        elif xh > max_xh:
            sys.stderr.write(
                f"  WARNING: x-height {a.size}mm on {ruling}mm {a.paper} rule will collide "
                f"between lines. --no-fit was passed, so rendering it anyway.\n")
    else:
        gap = xh / 0.50 * (a.line_height or 1.62)
    em = xh / 0.50
    m = list(spec.get("margins") or (None, None, None, None))
    for k, v in enumerate((a.margin_top, a.margin_right, a.margin_bottom, a.margin_left)):
        if v is not None:
            m[k] = v
    left = int(m[3] * px_per_mm) if m[3] is not None else int(W * 0.115)
    right = int(W - m[1] * px_per_mm) if m[1] is not None else int(W * 0.935)
    bottom = int(m[2] * px_per_mm) if m[2] is not None else int(H * 0.055)
    if ruling and spec.get("first") is not None and not (spec.get("grid") or spec.get("dots")):
        # the printed header band: the first rule is fixed, the writing starts on the next
        rule_top = spec["first"] * px_per_mm
        want = (m[0] * px_per_mm if m[0] is not None else rule_top) + gap * 0.75
        top = rule_top + max(1, math.ceil((want - rule_top) / gap)) * gap
    elif ruling:
        pitch = ruling * px_per_mm
        base = (spec.get("first") or 0.0) * px_per_mm
        want = (m[0] * px_per_mm if m[0] is not None else H * 0.085) + gap * 0.6
        top = base + max(1, math.ceil((want - base) / pitch)) * pitch
        if spec.get("first") is None and m[0] is None:
            top = int(round(int(H * 0.085) / gap) * gap) or int(gap)   # land on a rule
        rule_top = top
    else:
        top = int(m[0] * px_per_mm + gap * 0.75) if m[0] is not None else int(H * 0.085)
        rule_top = top
    return dict(left=left, right=right, top=top, bottom=bottom, gap=gap,
                rule_top=rule_top), xh, em


def main():
    ap = build_parser()
    a = ap.parse_args()
    given = {x.lstrip('-').split("=")[0].replace('-', '_') for x in sys.argv if x.startswith('--')}
    if a.preset:
        pre = PRESETS.get(a.preset)
        if not pre:
            sys.exit(f"unknown preset {a.preset}; have {', '.join(PRESETS)}")
        for k, v in pre.items():
            if k not in given:
                setattr(a, k, v)
    if a.realism:
        for k, v in REALISM[a.realism].items():
            if k not in given:
                setattr(a, k, v)
    for k, v in hw_effects.EFFECTS[a.effect].items():
        if k not in given:
            setattr(a, k, v)

    text = a.text
    if a.file:
        text = open(os.path.expanduser(a.file), encoding="utf-8").read()
    if text is None:
        text = sys.stdin.read()
    if not text.strip():
        sys.exit("no text")

    seed = a.seed if a.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    nrng = np.random.RandomState(seed & 0x7FFFFFFF)

    mm = PAGE_MM[a.pagesize]
    if a.landscape:
        mm = (mm[1], mm[0])
    px_per_mm = a.dpi / 25.4
    W, H = int(mm[0] * px_per_mm), int(mm[1] * px_per_mm)
    geo, xh, em = geometry(a, W, H, px_per_mm, a.size * px_per_mm)

    bank_at = build_bank_factory(a, em, nrng, text)
    bank = bank_at(1.0)[0]
    hand = Hand(rng, em, a.messiness, a.slant, a.sag, a.pressure, a.drift, a.linestart)
    if PAPERS[a.paper].get("mm"):
        # on ruled paper the rule pulls the baseline back: an unruled wander of 0.34 em let a
        # tall-ascender hand (Reenie) drop "you" onto the "has" of the next line (2026-09-24)
        hand.baseline.scale = min(hand.baseline.scale, geo["gap"] * 0.12)
    capture = "print" if a.mode == "photo" and "capture" not in given else a.capture
    paper_img = load_paper_image(a.paper_image, W, H) if a.paper_image else None
    cfg = dict(W=W, H=H, dpi=a.dpi, paper=a.paper, ink=a.ink, line_gap=geo["gap"],
               top=geo["top"], bottom=geo["bottom"], left=geo["left"], right=geo["right"],
               rule_top=geo["rule_top"], bleed=a.bleed, pool=a.pool, skip=a.skip,
               grain=a.grain, showthrough=a.showthrough, capture=capture,
               word_space=a.word_space, ink_rgb=parse_ink(a.ink), fix_rgb=parse_ink(a.correct_ink),
               cursive=a.cursive, corrections=a.corrections, highlight=a.highlight,
               restart=a.restart, smudge=a.smudge, texture=a.texture, shading=a.shading,
               blur=a.blur, ink_flow=a.ink_flow, holes=a.holes, mirror=a.mirror,
               margin_line=a.margin_line, align=a.align, hyphenate=a.hyphenate,
               paper_rgb=hw_paper.parse_color(a.paper_color, hw_paper.PAPER_COLORS),
               rule_rgb=hw_paper.hexrgb(a.rule_color) if a.rule_color else None,
               paper_img=paper_img, seed=seed, effect=a.effect, shadow=a.shadow,
               contrast=a.contrast,
               base_dir=os.path.dirname(os.path.abspath(os.path.expanduser(a.file))) if a.file else None)

    space_px = bank.advance(" ") * a.word_space
    comp = hw_doc.Composer(bank, geo["gap"], geo["left"], geo["right"], space_px, cfg)
    items = comp.compose(hw_doc.parse(text, plain=a.plain))
    semantic_corrections = any(getattr(it, "ink", "main") == "correction" for it in items)
    per_page = max(1, int((H - geo["top"] - geo["bottom"]) / geo["gap"]) + 1)
    pages_src = hw_doc.paginate(items, per_page)[:a.max_pages]

    imgs, prev, rates = [], None, []
    for i, pl in enumerate(pages_src):
        prng = random.Random(seed + i * 9176)
        pnrng = np.random.RandomState((seed + i * 9176) & 0x7FFFFFFF)
        hand.rng = prng
        img, ink, rate = render_page(pl, bank, hand, prng, pnrng, cfg, prev, bank_at, i)
        imgs.append(img); prev = ink; rates.append(rate)
        sys.stderr.write(f"  page {i+1}/{len(pages_src)}\n")

    scene_used = None
    if a.mode == "photo":
        import hw_scene
        imgs, scene_used = hw_scene.place_pages(imgs, a.scene, a.view, seed, a.dpi)

    out = os.path.expanduser(a.out)
    files = save_pages(imgs, out, a.dpi, a.quality)
    report = {"out": out, "pages": len(imgs), "seed": seed,
              "size_px": list(imgs[0].size), "dpi": a.dpi, "font": a.font, "capture": capture,
              "mode": a.mode, "scene": scene_used, "files": files,
              # what was actually used, so a run can be reproduced from its own output
              "glyphset": a.glyphset, "paper": a.paper, "ink": a.ink, "realism": a.realism,
              "cursive": a.cursive or 0, "corrections": a.corrections,
              "correct_ink": a.correct_ink if (a.corrections or semantic_corrections) else None,
              "highlight": a.highlight, "effect": a.effect, "paper_image": a.paper_image,
              # fraction of adjacent glyph pairs whose ink overlaps >50% of the narrower one.
              # Above ~0.06 the page starts to read as mush. This is the legibility gate.
              "collision_rate": round(sum(rates) / max(1, len(rates)), 4)}
    side = os.path.splitext(out)[0] + ".hyperwrite.json"
    try:
        json.dump(report, open(side, "w"), indent=2)
        report["sidecar"] = side
    except OSError:
        pass
    print(json.dumps(report, indent=2))

PRESETS = {
    "study-notebook": dict(paper="ruled", ink="black", size=4.3, slant=-2,
                           messiness=0.62, drift=0.16, wobble=0.68, variants=14,
                           pressure=0.85, grain=0.16, skip=0.10, bleed=0.65,
                           pool=0.65, showthrough=0.25, linestart=0.55,
                           cursive=0, capture="scan", font="patrick"),
    "student":  dict(paper="college", ink="blue", size=3.9, slant=-4, messiness=0.95,
                     drift=0.26, wobble=1.0, variants=20, pressure=1.0, grain=0.25,
                     skip=0.25, showthrough=0.7, capture="photo", glyphset="casual-blue"),
    "neat":     dict(paper="ruled",   ink="darkblue", messiness=0.55, slant=-3, capture="scan",
                     size=4.6, skip=0.15),
    "letter":   dict(paper="cream",   ink="blueblack", messiness=0.75, slant=-8, sag=0.35,
                     capture="scan", size=5.0, paper_note=None) ,
    "journal":  dict(paper="ruled",   ink="black", messiness=1.0, slant=-2, capture="scan"),
    "exam":     dict(paper="ruled",   ink="blue",  messiness=1.7, slant=-9, capture="photo",
                     skip=0.7, size=4.2),
    "pencil":   dict(paper="grid",    ink="pencil", messiness=1.1, slant=-4, capture="scan",
                     bleed=0.4, pool=0.5, grain=0.45),
    # Measured from a phone photo of a real page, not chosen by eye:
    # scripts/measure.py IMG_6944.HEIC --paper college   (2026-09-21)
    # rule 7.1mm, x-height 2.3mm, slant -2 deg, ink RGB (35,35,33), show-through 1.52.
    #
    # Then tuned purely for the match score, which reached 81/100 and produced a page the
    # owner of the handwriting called unreadable: at a 3.4mm x-height, grain 0.5 with
    # pressure 1.3 and a 0.16 warp bit holes in the strokes and `product` read as `produLt`.
    # These numbers are the readable settings, chosen by looking. READABILITY IS THE
    # CONSTRAINT; the score is what gets maximised inside it, never the other way round.
    "henry":    dict(paper="college", ink="black", size=3.8, slant=-2, messiness=0.75,
                     drift=0.22, wobble=0.9, variants=20, pressure=0.9, grain=0.2,
                     skip=0.12, bleed=0.7, pool=0.7, showthrough=0.5, linestart=0.6,
                     capture="scan", glyphset="casual-blue"),
}
for _p in PRESETS.values():
    _p.pop("paper_note", None)

if __name__ == "__main__":
    main()
