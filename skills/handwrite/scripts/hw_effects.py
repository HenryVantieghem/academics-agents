#!/usr/bin/env python3
"""
hw_effects — the page effects of saurabhdaware/text-to-handwriting (MIT), on the page array.

Upstream lays a CSS `linear-gradient(<angle>, #0008, #0000)` over the whole page before
html2canvas captures it. "Shadows" picks the angle anywhere in 0-360 degrees. "Scanner" holds it
to 50-120 degrees, so the lit side never lands on the left margin, and then raises the contrast
of every channel by 0.55: the look of a phone scanner app, paper blown to white and ink dark.
The constants below are theirs; the angle comes from the seed, so a page is repeatable.

    --effect shadows | scanner | none      upstream's three choices
    --shadow 1.0                           gradient strength, 1 = upstream's #0008
    --contrast 0.55                        upstream's scanner contrast, 0 = off
"""
import math, random

import numpy as np

# explicit flags win over these, the same way they win over --preset and --realism
EFFECTS = {
    "none":    {},
    "shadows": {"shadow": 1.0},
    "scanner": {"shadow": 1.0, "contrast": 0.55, "capture": "print"},
}
ANGLES = {"scanner": (50, 120)}                 # everything else: the whole circle
SHADOW_ALPHA = 0x88 / 255.0                    # upstream's #0008 at the dark end
MID = 128 / 255.0                              # contrastImage() pivots on 128


def effect_rng(seed, page_no):
    """Its own stream, so turning an effect on never changes the writing."""
    return random.Random((seed * 1_000_003 + page_no) ^ 0x5AD0)


def css_gradient(H, W, deg):
    """Where each pixel sits along a CSS linear-gradient at `deg`: 0 at the start colour,
    1 at the end. 0deg points up and 90deg right; the line runs through the centre and is
    exactly long enough for the far corners to land on 0 and 1, as CSS draws it."""
    a = math.radians(deg)
    dx, dy = math.sin(a), -math.cos(a)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    proj = (xx + 0.5 - W / 2.0) * dx + (yy + 0.5 - H / 2.0) * dy     # pixel centres
    length = abs(W * dx) + abs(H * dy)
    return np.clip(proj / max(length, 1e-6) + 0.5, 0.0, 1.0)


def shadow(img, rng, strength, effect):
    """Darken the page toward one side: black at SHADOW_ALPHA x strength, fading to clear."""
    if strength <= 0:
        return img
    lo, hi = ANGLES.get(effect, (0, 360))
    t = css_gradient(img.shape[0], img.shape[1], rng.uniform(lo, hi))
    a = np.clip(SHADOW_ALPHA * strength * (1.0 - t), 0.0, 1.0)
    return img * (1.0 - a)[..., None]


def contrast(img, amount):
    """Upstream's contrastImage(): factor (c*255 + 255) / (255.01 - c*255) about 128."""
    if amount <= 0:
        return img
    c = min(amount, 0.99) * 255.0
    factor = (c + 255.0) / (255.01 - c)
    return np.clip(factor * (img - MID) + MID, 0.0, 1.0)
