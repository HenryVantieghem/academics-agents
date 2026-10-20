#!/usr/bin/env python3
"""
hw_ink — the pen: smooth noise, joins between letters, and the Pen that writes one page.

Split out of hyperwrite.py (2026-09-24) when documents grew headings, lists, tables and maths:
hw_doc decides WHERE each thing goes, the Pen decides how a hand writes it.
"""
import math

import numpy as np
from PIL import Image

# ------------------------------------------------------------------ smooth noise
class Drift:
    """Value noise. A real baseline wanders on a slow curve; per-glyph white noise reads as
    a ransom note. Realism is not the amount of error, it is the CORRELATION of the error."""
    def __init__(self, rng, scale=1.0, step=40.0):
        self.rng, self.scale, self.step, self.a = rng, scale, step, {}
    def _anchor(self, i):
        if i not in self.a:
            self.a[i] = self.rng.uniform(-1, 1)
        return self.a[i]
    def at(self, t):
        x = t / self.step
        i = math.floor(x); f = x - i
        f = f * f * (3 - 2 * f)
        return (self._anchor(i) * (1 - f) + self._anchor(i + 1) * f) * self.scale

def value_noise_2d(rng, h, w, cells, octaves=1):
    """Low-frequency 2-D noise in [-1,1], built by upsampling a small random grid.
    Used for paper fibre, lighting gradients and glyph displacement fields."""
    out = np.zeros((h, w), np.float32)
    amp, c = 1.0, cells
    total = 0.0
    for _ in range(octaves):
        g = rng.uniform(-1, 1, (max(2, int(c)), max(2, int(c)))).astype(np.float32)
        up = np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC), np.float32)
        out += up * amp
        total += amp
        amp *= 0.5; c *= 2
    return out / max(total, 1e-6)

def bilinear_sample(src, sx, sy):
    """Sample src (float32 HxW) at fractional coords. numpy only — no scipy dependency."""
    h, w = src.shape
    sx = np.clip(sx, 0, w - 1.001); sy = np.clip(sy, 0, h - 1.001)
    x0 = sx.astype(np.int32); y0 = sy.astype(np.int32)
    x1 = x0 + 1; y1 = y0 + 1
    fx = (sx - x0)[..., None][..., 0]; fy = (sy - y0)[..., None][..., 0]
    return (src[y0, x0] * (1 - fx) * (1 - fy) + src[y0, x1] * fx * (1 - fy) +
            src[y1, x0] * (1 - fx) * fy      + src[y1, x1] * fx * fy)

# ------------------------------------------------------------------ joins
def stroke_edges(ga, baseline_row, band):
    """Where a pen would leave this letter and enter the next.

    Cursive is not a font property — it is what happens BETWEEN letters. Find the ink nearest
    the baseline on each side of the glyph; those are the two points a real hand connects.
    """
    h, w = ga.shape
    lo = max(0, int(baseline_row - band))
    hi = min(h, int(baseline_row + band * 0.55))
    if hi <= lo:
        return None
    strip = ga[lo:hi]
    cols = np.nonzero(strip.max(axis=0) > 0.30)[0]
    if len(cols) == 0:
        return None
    def row_at(c):
        col = strip[:, c]
        idx = np.nonzero(col > 0.30)[0]
        return lo + float(idx.mean()) if len(idx) else baseline_row
    x0, x1 = int(cols[0]), int(cols[-1])
    return (x0, row_at(x0)), (x1, row_at(x1))

def draw_join(alpha, p0, p1, width, rng, dip=0.32):
    """Lay a pen stroke from one letter's exit to the next letter's entry.

    A quadratic curve that sags below the straight line, because a hand travelling right
    drops into the baseline and comes back up. A straight line reads as a typographic
    underscore; the sag is what makes it read as handwriting.
    """
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    if dx <= 0 or dx > width * 22:
        return
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0 + dx * dip * rng.uniform(0.6, 1.25)
    n = max(4, int(dx * 1.6))
    H, W = alpha.shape
    r = max(0.6, width * 0.5)
    ri = int(math.ceil(r)) + 1
    yy, xx = np.mgrid[-ri:ri + 1, -ri:ri + 1].astype(np.float32)
    disk = np.clip(r + 0.5 - np.sqrt(xx ** 2 + yy ** 2), 0, 1)
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        px = mt * mt * x0 + 2 * mt * t * cx + t * t * x1
        py = mt * mt * y0 + 2 * mt * t * cy + t * t * y1
        # the pen lightens as it travels between letters and presses again on the next one
        w8 = 0.55 + 0.45 * abs(2 * t - 1)
        ix, iy = int(round(px)), int(round(py))
        a0, a1 = max(0, iy - ri), min(H, iy + ri + 1)
        b0, b1 = max(0, ix - ri), min(W, ix + ri + 1)
        if a1 <= a0 or b1 <= b0:
            continue
        sub = disk[a0 - (iy - ri):a1 - (iy - ri), b0 - (ix - ri):b1 - (ix - ri)]
        reg = alpha[a0:a1, b0:b1]
        np.maximum(reg, sub * w8, out=reg)

# ------------------------------------------------------------------ the pen
class Pen:
    """Everything that puts ink on one page. hw_doc decides WHERE things go; the pen decides
    how a hand writes them: variant choice, slant, baseline drift, pressure, joins, and the
    collision count that is the engine's legibility gate."""

    def __init__(self, bank, hand, rng, gnrng, cfg, W, H, bank_at):
        self.bank, self.hand, self.rng, self.gnrng, self.cfg = bank, hand, rng, gnrng, cfg
        self.bank_at = bank_at
        self.px = bank.px
        self.xh = bank.px * 0.5
        self.nib = max(0.9, self.xh * 0.105)          # pen stroke half-width, for joins and rules
        sw = getattr(bank, "stroke_px", None)
        if sw:
            # drawn strokes take the face's own pen width, measured, not assumed
            self.nib = max(0.8, min(self.nib, sw / 1.45))
        self.space = bank.advance(" ") * cfg["word_space"]
        self.alpha = np.zeros((H, W), np.float32)
        # a second layer for a second pen. Real marked-up pages are two-colour: the page this
        # engine was measured against literally says "First attempt in Black / Corrections in Blue"
        self.alpha_fix = np.zeros((H, W), np.float32)
        self.alpha_hl = np.zeros((H, W), np.float32)
        self.pastes = []
        self.W, self.H = W, H
        self.y_top, self.frac = cfg["top"], 0.0
        # Legibility cannot be measured from the finished image: tesseract cannot read
        # handwriting at all (0.01 on a page a person reads fine) and a vision model reads
        # collided mush at 0.88 because it guesses the words from context. Both measured
        # 2026-09-21 and both discarded. The renderer, however, knows exactly where it put
        # every glyph — so collision is counted here, where it is exact and free.
        self.collisions = self.pairs = 0

    def at_row(self, y):
        self.frac = (y - self.cfg["top"]) / max(1.0, self.H - self.cfg["top"] - self.cfg["bottom"])

    def line_start(self, x0, k=1.0):
        # Line starts must be INDEPENDENT between lines. Driving them off the slant drift
        # (step ~11 em) made consecutive lines sample almost the same value, so every line
        # started in the same place and the measured scatter was 0.0004 of page width.
        h = self.hand
        return x0 + (abs(self.rng.gauss(0, 1.0)) * self.px * 0.30 * h.m - self.px * 0.06) \
            * h.linestart * k

    def word_gap(self, sp):
        return sp * (0.72 + 0.56 * self.rng.random())

    def _stamp(self, layer, ga, px0, py0):
        px1, py1 = px0 + ga.shape[1], py0 + ga.shape[0]
        sx0, sy0 = max(0, px0), max(0, py0)
        sx1, sy1 = min(self.W, px1), min(self.H, py1)
        if sx1 > sx0 and sy1 > sy0:
            sub = ga[sy0 - py0:sy1 - py0, sx0 - px0:sx1 - px0]
            reg = layer[sy0:sy1, sx0:sx1]
            np.maximum(reg, sub, out=reg)

    def _glyph_raster(self, unit, scale, wslant, first, word_press, x):
        """One written instance of `unit`: a fresh variant, sized, slanted and pressed."""
        hand, rng, fat = self.hand, self.rng, self.hand.fatigue(self.frac)
        bank, resid = self.bank_at(scale)
        g = bank.get(unit, rng.randrange(bank.variants))
        if g is None:
            return None
        garr, gox, goy = g
        sc = resid * (1.0 + hand.size_d.at(x) + rng.gauss(0, 0.012 * hand.m))
        rot = wslant + rng.gauss(0, 1.1 * hand.m * fat)
        gi = Image.fromarray((np.clip(garr, 0, 1) * 255).astype(np.uint8), "L")
        if abs(sc - 1.0) > 0.004:
            nw = max(1, int(gi.width * sc)); nh = max(1, int(gi.height * sc))
            gi = gi.resize((nw, nh), Image.LANCZOS)
            gox *= sc; goy *= sc
        if abs(rot) > 0.05:
            w0, h0 = gi.size
            gi = gi.rotate(rot, Image.BICUBIC, expand=True)
            gox += (gi.width - w0) / 2.0; goy += (gi.height - h0) / 2.0
        ga = np.asarray(gi, np.float32) / 255.0
        # pressure: the pen pushes harder and lighter on a slow wave
        k = max(0.0, min(1.0, 0.5 + hand.press.at(x)))
        k = max(0.0, min(1.0, k * word_press))
        if first and self.cfg["restart"] > 0:
            # the nib sat still for an instant before moving off
            k = min(1.0, k + 0.22 * self.cfg["restart"])
        # pressure swings the whole stroke; the fine field is ink sitting unevenly
        # in the paper's tooth, which is what stops a stroke reading as a fill
        ga = ga * (1.0 - 0.38 * hand.pressure + 0.55 * hand.pressure * k)
        if self.cfg["grain"] > 0 and ga.size > 16:
            gh, gw = ga.shape
            tooth = value_noise_2d(self.gnrng, gh, gw, max(3, gw // 2), octaves=2)
            ga = ga * (1.0 + tooth * 0.42 * self.cfg["grain"])
        return np.clip(ga, 0, 1), gox, goy

    def word(self, units, x, y, scale=1.0, style=frozenset(), squeeze=1.0):
        """Write one word with its baseline at y. Returns the x after it."""
        hand, rng, cfg = self.hand, self.rng, self.cfg
        fat = hand.fatigue(self.frac)
        px = self.px * scale
        wslant = hand.slant_bias + hand.slantd.at(x) * fat
        word_x0, prev_exit, placed = x, None, []
        # a word written slower is a shade darker; humans do not hold one speed
        word_press = 1.0 + rng.gauss(0, 0.07 * hand.m)
        if "bold" in style:
            word_press += 0.25
        for ci, u in enumerate(units):
            adv = self.bank.advance(u) * scale
            dy = (hand.baseline.at(x) * fat + rng.gauss(0, px * 0.007 * hand.m * fat)
                  - hand.sag * ((x - cfg["left"]) / max(1.0, cfg["right"] - cfg["left"])) * px)
            r = self._glyph_raster(u, scale, wslant, ci == 0, word_press, x) if u != " " else None
            if r is None:
                x += adv * squeeze
                placed = []
                continue
            ga, gox, goy = r
            px0 = int(round(x - gox)); py0 = int(round(y + dy - goy))
            self._stamp(self.alpha, ga, px0, py0)
            if "bold" in style:
                # a heavier hand goes over the letter twice, a hair apart
                self._stamp(self.alpha, ga, px0 + max(1, int(self.nib * 0.7)), py0)
            if cfg["cursive"] and len(u) == 1:
                e = stroke_edges(ga, goy, self.xh * scale * 0.55)
                if e is not None:
                    (ex0, ey0), (ex1, ey1) = e
                    entry = (px0 + ex0, py0 + ey0)
                    if prev_exit is not None:
                        draw_join(self.alpha, prev_exit, entry, self.nib * 1.15 * scale, rng,
                                  dip=0.30 * cfg["cursive"])
                    prev_exit = (px0 + ex1, py0 + ey1)
            # the glyph raster carries padding, so its BOX always overlaps its
            # neighbour's. Measure the tight INK extent instead, on x only —
            # vertical overlap is just "same line" and proves nothing.
            cols = np.nonzero(ga.max(axis=0) > 0.15)[0]
            if len(cols):
                ix0, ix1 = px0 + int(cols[0]), px0 + int(cols[-1]) + 1
                if placed:
                    qx0, qx1 = placed[-1]
                    ov = min(ix1, qx1) - max(ix0, qx0)
                    narrow = min(ix1 - ix0, qx1 - qx0)
                    self.pairs += 1
                    if ov > 0 and narrow > 0 and ov / narrow > 0.50:
                        self.collisions += 1
                placed.append((ix0, ix1))
            x += adv * squeeze * (1.0 - (fat - 1.0) * 0.045) + rng.gauss(0, px * 0.012 * hand.m)
        if cfg["corrections"] > 0 and len(units) > 3 and rng.random() < cfg["corrections"]:
            self.strike(word_x0, x, y, scale, fix=True)
        return x

    def strike(self, x0, x1, y, scale=1.0, fix=False):
        xh = self.xh * scale
        yb = y + self.hand.baseline.at(x0) * self.hand.fatigue(self.frac)
        wob = self.rng.uniform(-0.25, 0.25) * xh
        draw_join(self.alpha_fix if fix else self.alpha,
                  (x0 - xh * 0.12, yb - xh * 0.34 + wob), (x1 + xh * 0.12, yb - xh * 0.30 - wob),
                  self.nib * 1.7, self.rng, dip=self.rng.uniform(-0.06, 0.06))

    def decorate(self, style, x0, x1, y, scale):
        if "strike" in style:
            self.strike(x0, x1, y, scale)
        if "under" in style:
            yy = y + self.xh * scale * 0.28
            self.stroke([(x0 - 2, yy), ((x0 + x1) / 2, yy + self.xh * 0.08), (x1 + 3, yy - 1)], 0.9)
        if "hl" in style:
            xh = self.xh * scale
            y0, y1 = int(y - xh * 1.25), int(y + xh * 0.35)
            a, b = max(0, int(x0 - xh * 0.2)), min(self.W, int(x1 + xh * 0.3))
            self.alpha_hl[max(0, y0):max(0, y1), a:b] = 0.8

    def glyph(self, unit, x, y, scale):
        """A lone character — maths, a list number — written without joins."""
        r = self._glyph_raster(unit, scale, self.hand.slant_bias * 0.5, False, 1.0, x)
        if r is not None:
            ga, gox, goy = r
            dy = self.rng.gauss(0, self.px * 0.006 * self.hand.m)
            self._stamp(self.alpha, ga, int(round(x - gox)), int(round(y + dy - goy)))

    def stroke(self, pts, weight=1.0, layer=None):
        """A pen line through points. It wanders on a SLOW curve across its length, never a
        per-pixel jitter: jitter reads as a zig-zag filter, and the vision judge called a table
        ruled that way "a digital font" (2026-09-24). The pen also lightens where it lifts."""
        if len(pts) < 2:
            return
        seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        total = max(1.0, sum(seg))
        step = max(1.5, self.nib * 0.8)
        dense, acc = [], 0.0
        for (xa, ya), (xb, yb), L in zip(pts, pts[1:], seg):
            n = max(1, int(L / step))
            for k in range(n):
                t = k / n
                dense.append((xa + (xb - xa) * t, ya + (yb - ya) * t, (acc + L * t) / total,
                              (xb - xa) / max(L, 1e-6), (yb - ya) / max(L, 1e-6)))
            acc += L
        xb, yb = pts[-1]
        dense.append((xb, yb, 1.0, dense[-1][3], dense[-1][4]))
        amp = self.xh * 0.05 * self.hand.m * min(1.0, total / (self.xh * 6))
        ph = [self.rng.uniform(0, 2 * math.pi) for _ in range(2)]
        cyc = [self.rng.uniform(0.6, 1.4), self.rng.uniform(1.8, 3.2)]
        out = []
        for x, y, t, dx, dy in dense:
            off = amp * (0.7 * math.sin(2 * math.pi * cyc[0] * t + ph[0])
                         + 0.3 * math.sin(2 * math.pi * cyc[1] * t + ph[1]))
            out.append((x - dy * off, y + dx * off, t))
        width = self.nib * 1.45 * weight
        for (xa, ya, ta), (xb, yb, _) in zip(out, out[1:]):
            lift = 0.8 * (0.78 + 0.22 * min(1.0, ta * 8, (1 - ta) * 8))
            self._segment((xa, ya), (xb, yb), width, layer, lift)

    def _segment(self, a, b, width, layer=None, ink=0.92):
        """Any direction, including straight down and backwards — draw_join only goes right."""
        layer = self.alpha if layer is None else layer
        H, W = layer.shape
        r = max(0.6, width * 0.5)
        ri = int(math.ceil(r)) + 1
        yy, xx = np.mgrid[-ri:ri + 1, -ri:ri + 1].astype(np.float32)
        disk = np.clip(r + 0.5 - np.sqrt(xx ** 2 + yy ** 2), 0, 1)
        n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) * 1.6))
        for i in range(n + 1):
            t = i / n
            ix, iy = int(round(a[0] + (b[0] - a[0]) * t)), int(round(a[1] + (b[1] - a[1]) * t))
            a0, a1 = max(0, iy - ri), min(H, iy + ri + 1)
            b0, b1 = max(0, ix - ri), min(W, ix + ri + 1)
            if a1 > a0 and b1 > b0:
                sub = disk[a0 - (iy - ri):a1 - (iy - ri), b0 - (ix - ri):b1 - (ix - ri)]
                np.maximum(layer[a0:a1, b0:b1], sub * ink, out=layer[a0:a1, b0:b1])

    def math(self, box, x, y):
        for op in box.ops:
            if op[0] == "g":
                self.glyph(op[1], x + op[2], y + op[3], op[4])
            else:
                self.stroke([(x + px, y + py) for px, py in op[1]], op[2])

    def marker(self, m, x, y, scale):
        if m in ("*", "•"):
            r = self.xh * 0.16
            cx, cy = x + self.xh * 0.3, y - self.xh * 0.45
            self.stroke([(cx - r, cy), (cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], 1.3)
        elif m == "-":
            yy = y - self.xh * 0.42
            self.stroke([(x, yy), (x + self.xh * 0.75, yy - self.xh * 0.04)], 1.0)
        else:
            for ch in m:
                self.glyph(ch, x, y, scale)
                x += self.bank.advance(ch) * scale

    def paste(self, path, x, y, w, h):
        self.pastes.append((path, int(x), int(y), int(w), int(h)))
