#!/usr/bin/env python3
"""
hw_paper — every paper the engine can write on, drawn to the millimetre.

The first eleven rows are ours and keep their original behaviour. The rest follow
handtextai's own paper catalog (`paper_families` in their editor bundle, read 2026-09-24): rule
pitch, rule colour and weight, where the first rule sits, the margin guides and the default
margins are theirs to the tenth of a millimetre, because those are facts about real stationery.

A spec's fields:
    bg          paper colour                 rule        rule colour (None = no ruling)
    mm          printed row pitch            xmm         column pitch for a grid
    rule_w      rule weight, mm              first       first rule's distance from the top, mm
    guides      [(side, offset_mm, rgb, weight_mm)] vertical margin lines
    margins     (top, right, bottom, left) mm, where the writing may go
    write_every how many printed rows one written line takes (5 mm grids: 2)
    dots        dots at the grid crossings instead of lines
"""
import numpy as np
from PIL import Image


def hexrgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


RED = (196, 120, 128)
PAPERS = {
    # ------------------------------------------------ ours, unchanged
    "ruled":     dict(bg=(253, 252, 248), rule=(150, 172, 200), mm=8.7, margin_rule=True),
    "grid":      dict(bg=(252, 252, 250), rule=(178, 196, 214), mm=5.0, grid=True, write_every=2),
    "legal":     dict(bg=(253, 244, 196), rule=(120, 150, 190), mm=8.7, margin_rule=True),
    "dotted":    dict(bg=(252, 251, 247), rule=(186, 190, 196), mm=5.0, dots=True, write_every=2),
    "graph":     dict(bg=(251, 252, 250), rule=(176, 200, 216), mm=5.0, grid=True, write_every=2),
    "moleskine": dict(bg=(246, 238, 220), rule=(196, 180, 148), mm=5.0, dots=True, write_every=2),
    "engineer":  dict(bg=(240, 246, 236), rule=(150, 186, 156), mm=6.35, margin_rule=True,
                      grid=True, write_every=2),
    "cream":     dict(bg=(248, 241, 226), rule=None, mm=None),
    "blank":     dict(bg=(253, 252, 250), rule=None, mm=None),
    # ------------------------------------------------ handtextai's catalog
    "college":   dict(bg=hexrgb("fffef9"), rule=hexrgb("97b4e6"), mm=7.1, rule_w=0.2, first=37.5,
                      guides=[("left", 23, hexrgb("d8707a"), 0.25)], margins=(37.5, 5.8, 7.6, 29)),
    "wide":      dict(bg=hexrgb("fffef9"), rule=hexrgb("97b4e6"), mm=8.7, rule_w=0.2, first=37.5,
                      guides=[("left", 23, hexrgb("d8707a"), 0.25)], margins=(37.5, 5.8, 7.6, 29)),
    "feint":     dict(bg=hexrgb("fffefb"), rule=hexrgb("c3edf1"), mm=9.0, rule_w=0.18, first=27,
                      guides=[("left", 25, hexrgb("e7a7af"), 0.22)], margins=(27, 8, 8, 29)),
    "lineatur25": dict(bg=hexrgb("fffefb"), rule=hexrgb("a4aec2"), mm=9.0, rule_w=0.18, first=34,
                       guides=[("right", 50, hexrgb("8893a7"), 0.22)], margins=(18, 55, 18, 10)),
    "lineatur27": dict(bg=hexrgb("fffefb"), rule=hexrgb("a4aec2"), mm=9.0, rule_w=0.18, first=18,
                       guides=[("left", 23, hexrgb("8893a7"), 0.22),
                               ("right", 23, hexrgb("8893a7"), 0.22)], margins=(18, 29, 18, 29)),
    "lineatur28": dict(bg=hexrgb("fffefc"), rule=hexrgb("c9d0da"), mm=5.0, xmm=5.0, rule_w=0.16,
                       first=0, grid=True, write_every=2,
                       guides=[("left", 23, hexrgb("9ba5b7"), 0.22),
                               ("right", 23, hexrgb("9ba5b7"), 0.22)], margins=(10, 29, 10, 29)),
    "cis-grid":  dict(bg=hexrgb("fffdfc"), rule=hexrgb("86b7ee"), mm=5.0, xmm=5.0, rule_w=0.18,
                      first=5, grid=True, write_every=2,
                      guides=[("right", 20, hexrgb("e45f6b"), 0.24)], margins=(5, 25, 5, 5)),
    "cis-ruled": dict(bg=hexrgb("fffdfc"), rule=hexrgb("8bbbf0"), mm=9.0, rule_w=0.18, first=8,
                      guides=[("right", 20, hexrgb("e45f6b"), 0.24)], margins=(8, 25, 8, 5)),
    "india":     dict(bg=hexrgb("fffdfb"), rule=hexrgb("b9c9e5"), mm=9.0, rule_w=0.18, first=34,
                      guides=[("left", 27.5, hexrgb("dc84aa"), 0.24)], margins=(30, 6, 8, 30)),
    "india-college": dict(bg=hexrgb("fffdfb"), rule=hexrgb("b9c9e5"), mm=9.0, rule_w=0.18,
                          first=34, guides=[("left", 27.5, hexrgb("dc84aa"), 0.24)],
                          margins=(34, 6, 10, 30)),
    "india-square": dict(bg=hexrgb("fffdfb"), rule=hexrgb("b9c9e5"), mm=12.0, xmm=12.0,
                         rule_w=0.16, first=0, grid=True,
                         guides=[("left", 24, hexrgb("dc84aa"), 0.24)], margins=(6, 6, 6, 30)),
    "squared5":  dict(bg=hexrgb("fffefc"), rule=hexrgb("d9e0e4"), mm=5.0, xmm=5.0, rule_w=0.16,
                      first=0, grid=True, write_every=2, margins=(10, 5, 5, 10)),
    "squared10": dict(bg=hexrgb("fffefc"), rule=hexrgb("d2dadd"), mm=10.0, xmm=10.0, rule_w=0.18,
                      first=0, grid=True, margins=(10, 5, 5, 10)),
    "plain":     dict(bg=(255, 255, 255), rule=None, mm=None, margins=(15, 15, 15, 20)),
}

# A sheet colour can be swapped on any paper: `--paper-color pink` or any #hex.
PAPER_COLORS = {
    "white": (255, 255, 255), "ivory": (255, 254, 249), "cream": (248, 241, 226),
    "yellow": (253, 244, 196), "pink": (252, 228, 234), "blue": (228, 239, 250),
    "green": (230, 245, 230), "grey": (238, 238, 236), "kraft": (206, 176, 136),
    "aged": (240, 228, 200),
}

PAGE_MM = {"a3": (297, 420), "a4": (210, 297), "a5": (148, 210), "a6": (105, 148),
           "letter": (215.9, 279.4), "legal": (215.9, 355.6), "tabloid": (279.4, 431.8),
           "postcard": (152.4, 101.6), "4x6": (101.6, 152.4), "5x7": (127, 177.8),
           "b5": (176, 250), "india": (180, 240)}


def parse_color(v, table):
    if v is None:
        return None
    s = str(v).strip()
    if s.startswith("#"):
        return hexrgb(s)
    if s not in table:
        raise SystemExit(f"unknown colour {s!r}: one of {', '.join(sorted(table))}, or #hex")
    return table[s]


def _hline(base, y, x0, x1, col, thick, alpha=0.72, skew=0.0):
    H, W = base.shape[:2]
    xs = np.arange(max(0, int(x0)), min(W, int(x1)))
    yy = y + (xs - x0) * skew
    for t in range(thick):
        idx = np.clip((yy + t).astype(np.int32), 0, H - 1)
        base[idx, xs] = base[idx, xs] * (1 - alpha) + col * alpha


def _vline(base, x, y0, y1, col, thick, alpha=0.7):
    H, W = base.shape[:2]
    ys = np.arange(max(0, int(y0)), min(H, int(y1)))
    for t in range(thick):
        idx = int(np.clip(x + t, 0, W - 1))
        base[ys, idx] = base[ys, idx] * (1 - alpha) + col * alpha


def draw_ruling(base, rng, spec, dpi, pitch, rule_top, left_margin):
    """Rules are PRINTED: flat, exactly parallel, a hair off-register. Ink goes on top later.

    `pitch` is the printed row pitch in px, `rule_top` the y of the first rule."""
    if spec.get("rule") is None or not pitch:
        return
    H, W = base.shape[:2]
    pxmm = dpi / 25.4
    col = np.array(spec["rule"], np.float32) / 255.0
    thick = max(1, int(round(spec.get("rule_w", 0.2) * pxmm * 0.9)))
    skew = rng.uniform(-0.0006, 0.0006)
    fullpage = spec.get("grid") or spec.get("dots")
    y = rule_top % pitch if fullpage else rule_top
    if spec.get("dots"):
        r = max(1, int(round(dpi / 300)))
        gy = y
        while gy < H:
            gx = left_margin % pitch
            while gx < W:
                y0, x0 = int(gy) - r, int(gx) - r
                if 0 <= y0 and y0 + 2 * r + 1 <= H and 0 <= x0 and x0 + 2 * r + 1 <= W:
                    base[y0:y0 + 2 * r + 1, x0:x0 + 2 * r + 1] = (
                        base[y0:y0 + 2 * r + 1, x0:x0 + 2 * r + 1] * 0.35 + col * 0.65)
                gx += pitch
            gy += pitch
    else:
        while y < H - (0 if fullpage else pitch * 0.4):
            _hline(base, y, 0, W, col, thick, 0.72, skew)
            y += pitch
        if spec.get("grid"):
            xp = (spec.get("xmm") or pitch / pxmm) * pxmm
            x = (left_margin % xp) if spec.get("xmm") is None else 0.0
            while x < W:
                _vline(base, x, 0, H, col, thick, 0.68)
                x += xp
    for side, off, gcol, gw in spec.get("guides", []):
        gx = off * pxmm if side == "left" else W - off * pxmm
        _vline(base, gx, 0, H, np.array(gcol, np.float32) / 255.0,
               max(1, int(round(gw * pxmm))), 0.75)
    if spec.get("margin_rule") and not spec.get("guides"):
        mx = int(left_margin - pitch * 0.55)
        _vline(base, mx, 0, H, np.array(RED, np.float32) / 255.0,
               max(1, int(round(dpi / 240))), 0.75)


def punch_holes(base, dpi, landscape=False):
    """US three-hole punch: 6 mm holes, 108 mm apart, 9.5 mm in from the edge. A hole shows
    whatever is under the sheet, so it is drawn as a soft grey shadowed disc, not white."""
    H, W = base.shape[:2]
    pxmm = dpi / 25.4
    r = 3.0 * pxmm
    cx = 9.5 * pxmm
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for dy in (-108, 0, 108):
        cy = H / 2 + dy * pxmm
        if cy - r < 0 or cy + r > H:
            continue
        y0, y1 = int(cy - r - 3), int(cy + r + 3)
        x0, x1 = int(cx - r - 3), int(cx + r + 3)
        d = np.sqrt((xx[y0:y1, x0:x1] - cx) ** 2 + (yy[y0:y1, x0:x1] - cy) ** 2)
        hole = np.clip(r - d + 0.5, 0, 1)[..., None]
        rim = np.clip(1 - np.abs(d - r) / 2.0, 0, 1)[..., None] * 0.25
        dark = np.array([0.58, 0.57, 0.55], np.float32)
        reg = base[y0:y1, x0:x1]
        base[y0:y1, x0:x1] = reg * (1 - hole) + dark * hole - rim * 0.2 * (1 - hole)


def paper_image(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
