#!/usr/bin/env python3
"""
measure — read a photo of a real handwritten page and print the flags that reproduce it.

"Make it look like this" is otherwise a matter of taste, and taste does not survive a week.
This measures the page: the ink colour, the slant, the x-height against the ruling, the word
gap, how far the baseline wanders, how much paper shows through the ink, and how much of the
verso bleeds through. Then it prints a hyperwrite command.

    measure.py ~/Downloads/notes.jpg --name my-hand

It deskews and crops the page itself, so a phone photo taken at an angle is fine. HEIC is
converted through `sips` on macOS.
"""
import argparse, json, math, os, subprocess, sys, tempfile

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# hyperwrite's named inks, so we can report the nearest one
INKS = {"blue": (28, 44, 122), "darkblue": (18, 28, 78), "black": (22, 22, 26),
        "blueblack": (24, 34, 66), "pencil": (74, 74, 80), "red": (140, 26, 30),
        "green": (26, 82, 54), "brown": (78, 52, 34)}
# rule spacing of the common papers, in mm — the ruling is the only absolute scale in a photo
RULINGS = {"college": 7.1, "ruled": 8.7, "wide": 8.7, "grid": 5.0, "legal": 8.7}

def load(path):
    p = os.path.expanduser(path)
    if p.lower().endswith((".heic", ".heif")):
        out = os.path.join(tempfile.mkdtemp(), "conv.png")
        subprocess.run(["sips", "-s", "format", "png", p, "--out", out],
                       capture_output=True, check=True)
        p = out
    return Image.open(p).convert("RGB")

def orient_and_crop(img, max_side=2400):
    """Find the page in the photo, rotate it upright, crop to it.

    A phone photo of a notebook is mostly desk. Everything measured below is a ratio against
    the ruling or the x-height, so a wrong crop does not merely add noise — it changes the
    scale and every number comes out wrong.
    """
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    g = np.asarray(img.convert("L"), np.float32)
    thr = float(np.percentile(g, 72))
    bright = g > thr
    cols = np.nonzero(bright.sum(0) > bright.shape[0] * 0.30)[0]
    rows = np.nonzero(bright.sum(1) > bright.shape[1] * 0.30)[0]
    if len(cols) > 20 and len(rows) > 20:
        img = img.crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))
    # text lines run along the longer axis of the writing, not of the paper: decide by which
    # orientation gives the stronger periodic row profile
    a = ink_alpha(img)
    if a is None:
        return img
    def linescore(m):
        p = m.sum(1).astype(np.float32)
        if p.max() <= 0:
            return 0.0
        p = p / p.max()
        f = np.abs(np.fft.rfft(p - p.mean()))
        return float(f[2:len(f) // 3].max()) if len(f) > 6 else 0.0
    m = a > 0.25
    if linescore(m.T) > linescore(m) * 1.25:
        img = img.transpose(Image.ROTATE_270)
    return img

def ink_alpha(img):
    g = np.asarray(img.convert("L"), np.float32) / 255.0
    bg = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(29)), np.float32) / 255.0
    d = np.clip(bg - g, 0, 1)
    hi = float(np.percentile(d, 99.6))
    return None if hi < 0.04 else np.clip(d / hi, 0, 1)

def deskew(img, alpha):
    """Small rotation so the ruled lines are level. Measured over +/-4 degrees."""
    best, ang = -1, 0.0
    m = (alpha > 0.25).astype(np.float32)
    for a in np.arange(-4.0, 4.01, 0.25):
        r = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).rotate(a, Image.BILINEAR),
                       np.float32)
        p = r.sum(1)
        v = float(p.var())
        if v > best:
            best, ang = v, float(a)
    if abs(ang) > 0.2:
        img = img.rotate(ang, Image.BICUBIC, fillcolor=(250, 249, 246))
    return img, ang

def rule_spacing(img):
    """Printed rules are long, straight, level and evenly spaced; handwriting is none of those.
    Returns the spacing in pixels, or None on unruled paper."""
    a = np.asarray(img.convert("L"), np.float32) / 255.0
    bg = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(29)), np.float32) / 255.0
    faint = np.clip(bg - a, 0, 1)
    # rules are FAINT: dark enough to see, far lighter than ink
    band = ((faint > 0.035) & (faint < 0.16)).astype(np.float32)
    prof = band.sum(1)
    prof = prof - prof.mean()
    if prof.std() < 1e-6:
        return None
    f = np.abs(np.fft.rfft(prof))
    f[:4] = 0
    k = int(np.argmax(f))
    if k < 4:
        return None
    sp = len(prof) / k
    return sp if 8 < sp < len(prof) / 6 else None

def slant_degrees(alpha):
    """Shear the ink and find the angle where vertical strokes line up best — the column
    projection gets spikiest exactly when the writing has been straightened."""
    m = (alpha > 0.3).astype(np.float32)
    h, w = m.shape
    ys = np.arange(h, dtype=np.float32)[:, None] - h / 2
    best, ang = -1.0, 0.0
    for a in np.arange(-22.0, 22.01, 1.0):
        sh = math.tan(math.radians(a))
        xs = (np.arange(w, dtype=np.float32)[None, :] + ys * sh)
        idx = np.clip(xs.astype(np.int32), 0, w - 1)
        p = np.take_along_axis(m, idx, axis=1).sum(0)
        v = float((p ** 2).sum())
        if v > best:
            best, ang = v, float(a)
    return -ang

def text_rows(mask):
    prof = mask.sum(1).astype(np.float32)
    thr = max(3.0, prof.max() * 0.06)
    out, on = [], False
    for y, p in enumerate(prof):
        if p > thr and not on:
            on, s = True, y
        elif p <= thr and on:
            on = False
            if y - s > 4:
                out.append((s, y))
    return out

def measure(path, paper_hint=None):
    img0 = load(path)
    img = orient_and_crop(img0)
    a = ink_alpha(img)
    if a is None:
        sys.exit("no ink found — is this a photo of a written page?")
    img, skew = deskew(img, a)
    a = ink_alpha(img)
    mask = a > 0.25
    H, W = mask.shape

    px = np.asarray(img, np.float32)
    dark = px[a > 0.55]
    ink_rgb = [float(x) for x in np.median(dark, axis=0)] if len(dark) > 50 else [30, 30, 40]
    nearest = min(INKS, key=lambda k: sum((ink_rgb[i] - INKS[k][i]) ** 2 for i in range(3)))

    sp = rule_spacing(img)
    paper = paper_hint or ("college" if sp else "blank")
    px_per_mm = (sp / RULINGS.get(paper, 7.1)) if sp else None

    rows = text_rows(mask)
    heights = [b - t for t, b in rows if b - t > 4]
    # an ink band holds ascenders and descenders; the x-height is roughly 45% of it
    xh_px = float(np.median(heights)) * 0.45 if heights else None
    gaps = np.diff([(t + b) / 2 for t, b in rows]) if len(rows) > 2 else []
    line_gap_px = float(np.median(gaps)) if len(gaps) else None

    slant = slant_degrees(a)

    import judge as J
    d, jm = J.ink_mask(img)
    gu, n = J.m_glyph_uniqueness(d, jm)
    flat = J.m_ink_flatness(d, jm)
    wander = J.m_baseline_wander(d, jm)
    life = J.m_paper_life(img)

    # show-through: faint ink-coloured marks in the gaps BETWEEN text rows
    inter = np.ones(H, bool)
    for t, b in rows:
        inter[max(0, t - 2):min(H, b + 2)] = False
    between = a[inter] if inter.sum() > 100 else np.array([0.0])
    showthrough = float(np.clip((between > 0.12).mean() * 26, 0, 1.6))

    out = {
        "source": os.path.basename(path),
        "page_px": [W, H],
        "deskew_deg": round(skew, 2),
        "ink_rgb": [round(x) for x in ink_rgb],
        "ink_nearest": nearest,
        "paper": paper,
        "rule_spacing_px": round(sp, 1) if sp else None,
        "px_per_mm": round(px_per_mm, 2) if px_per_mm else None,
        "x_height_mm": round(xh_px / px_per_mm, 2) if (xh_px and px_per_mm) else None,
        "line_gap_px": round(line_gap_px, 1) if line_gap_px else None,
        "slant_deg": round(slant, 1),
        "text_rows": len(rows),
        "glyph_uniqueness": round(gu, 4) if gu else None,
        "ink_flatness": round(flat, 4) if flat else None,
        "baseline_wander": round(wander, 4) if wander else None,
        "paper_life": round(life, 4) if life else None,
        "showthrough": round(showthrough, 2),
        "glyphs_measured": n,
    }
    return out, img

def to_flags(m):
    """Map the measurements onto hyperwrite's knobs. Each mapping is a ratio against something
    measured, never a taste call — so a different page gives different flags for a reason."""
    f = {}
    f["--paper"] = m["paper"]
    f["--ink"] = m["ink_nearest"]
    if m["x_height_mm"]:
        f["--size"] = round(max(3.2, min(7.0, m["x_height_mm"])), 1)
    f["--slant"] = int(round(max(-16, min(8, m["slant_deg"]))))
    if m["baseline_wander"]:
        # judge's real-hand anchor is 0.055; scale our default 0.34 against what this page does
        f["--drift"] = round(max(0.12, min(0.55, 0.34 * (m["baseline_wander"] / 0.055))), 2)
    if m["ink_flatness"]:
        f["--pressure"] = round(max(0.4, min(1.8, m["ink_flatness"] / 0.087)), 2)
    if m["paper_life"]:
        f["--grain"] = round(max(0.1, min(0.8, 0.45 * (m["paper_life"] / 0.0133))), 2)
    f["--showthrough"] = round(m["showthrough"], 2)
    f["--capture"] = "photo"
    return f

def main():
    ap = argparse.ArgumentParser(description="measure a real handwritten page into flags")
    ap.add_argument("image")
    ap.add_argument("--paper", default=None, choices=sorted(RULINGS) + ["blank", "cream"])
    ap.add_argument("--name", default=None, help="also print a glyphmint style prompt")
    ap.add_argument("--save-upright", default=None, help="write the deskewed crop here")
    a = ap.parse_args()
    m, img = measure(a.image, a.paper)
    flags = to_flags(m)
    if a.save_upright:
        img.save(os.path.expanduser(a.save_upright))
        m["upright"] = a.save_upright
    m["flags"] = flags
    m["command"] = ("python3 hyperwrite.py --file YOUR.txt --out out.pdf --seed 7 "
                    + " ".join(f"{k} {v}" for k, v in flags.items()))
    if a.name:
        lean = "strongly right-slanted" if m["slant_deg"] < -7 else \
               "slightly right-slanted" if m["slant_deg"] < -2 else "upright"
        m["mint"] = (f'python3 glyphmint.py mint --name {a.name} --repeats 3 '
                     f'--ink "{m["ink_nearest"]} ballpoint pen" '
                     f'--style "{lean} everyday handwriting, rounded and quickly written"')
    print(json.dumps(m, indent=2))

if __name__ == "__main__":
    main()
