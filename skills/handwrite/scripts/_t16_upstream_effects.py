#!/usr/bin/env python3
"""T16: text-to-handwriting's page effects and paper image, ported 2026-09-28, plus the seed.

    python3 _t16_upstream_effects.py <scripts dir> <tmp dir>

The seed check is a bug that happened: GlyphBank seeded each letter's warp from hash(ch), and
str hashes are salted per process, so one --seed drew a different hand on every run
(collision_rate 0.0159, 0.0032, 0.0095 for the same page, 2026-09-28).
"""
import json, os, subprocess, sys

import numpy as np
from PIL import Image

HERE, TMP = sys.argv[1], sys.argv[2]
sys.path.insert(0, HERE)
import hw_effects                                                     # noqa: E402

TEXT = ("Thank you so much for the birthday flowers. They arrived on Tuesday morning and "
        "the whole kitchen still smells like spring.\n\nCome and visit when the weather turns.")
src = os.path.join(TMP, "t16.txt")
open(src, "w").write(TEXT)


def render(name, *flags, env=None):
    out = os.path.join(TMP, f"t16-{name}.png")
    r = subprocess.run([sys.executable, os.path.join(HERE, "hyperwrite.py"), "--file", src,
                        "--out", out, "--seed", "5", "--dpi", "90", "--max-pages", "1",
                        "--paper", "plain", "--showthrough", "0", *flags],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"{name}: {r.stderr[-400:]}"
    return json.loads(r.stdout), np.asarray(Image.open(out).convert("L"), np.float32)


# CSS geometry: 90deg runs left to right, 180deg top to bottom, start colour at t = 0
g = hw_effects.css_gradient(40, 60, 90)
assert g[:, 0].max() < 0.02 and g[:, -1].min() > 0.98, "90deg should run left to right"
g = hw_effects.css_gradient(40, 60, 180)
assert g[0].max() < 0.02 and g[-1].min() > 0.98, "180deg should run top to bottom"

rep0, none = render("none", "--capture", "print")
rep1, shad = render("shadows", "--capture", "print", "--effect", "shadows")
rep2, scan = render("scanner", "--effect", "scanner")

assert rep2["capture"] == "print", "scanner should imply a clean capture unless --capture is given"


def box(a, r):
    k = np.ones(2 * r + 1, np.float32) / (2 * r + 1)
    a = np.apply_along_axis(np.convolve, 0, np.pad(a, r, mode="edge"), k, "valid")
    return np.apply_along_axis(np.convolve, 1, a, k, "valid")


# an effect lights the page; it must never move a letter. With identical writing the ratio of
# the two pages IS the gradient, smooth everywhere; a moved letter is a sharp spike in it.
ratio = shad / np.maximum(none, 1.0)
lit = none > 40                                                   # uint8 rounding in deep ink
spikes = np.abs(ratio - box(ratio, 3))[lit]
assert np.percentile(spikes, 99.95) < 0.06, "the shadow changed the writing, not only the light"
lo, hi = np.percentile(ratio, 0.1), np.percentile(ratio, 99.9)     # the two far corners
assert lo < 0.62, f"darkest edge only {1 - lo:.0%} darker; upstream's shadow reaches 53%"
assert hi > 0.97, f"the lit side is {1 - hi:.0%} darker; the gradient should fade to clear"

# scanner: contrast blows the paper to white and pushes the ink darker
white_none, white_scan = (none >= 254.5).mean(), (scan >= 254.5).mean()
assert white_scan > max(0.6, white_none + 0.2), f"white paper {white_none:.2f} -> {white_scan:.2f}"
ink_none, ink_scan = np.percentile(none, 0.5), np.percentile(scan, 0.5)
assert ink_scan < ink_none - 10, f"ink {ink_none:.0f} -> {ink_scan:.0f}, should get darker"

# an explicit flag still beats the effect's defaults
rep3, _ = render("scanner-scan", "--effect", "scanner", "--capture", "scan")
assert rep3["capture"] == "scan", "an explicit --capture must win over --effect scanner"

# the same seed is the same page in any process
env = dict(os.environ)
_, a = render("seed-a", "--capture", "print", env={**env, "PYTHONHASHSEED": "1"})
_, b = render("seed-b", "--capture", "print", env={**env, "PYTHONHASHSEED": "2"})
assert np.array_equal(a, b), "the same --seed drew a different page in another process"

# paper image: the photographed sheet is the page, scaled to COVER it and centred. A wide sheet
# with three bands leaves only the middle band on a portrait page; stretching it would put the
# outer bands at the page edges, and upstream's tiling would put the top-left corner there.
def paper_with(name, im):
    im.save(os.path.join(TMP, name), **({"exif": im.info["exif"]} if "exif" in im.info else {}))
    render(name[:-4], "--capture", "print", "--paper", "blank", "--paper-image",
           os.path.join(TMP, name))
    return np.asarray(Image.open(os.path.join(TMP, f"t16-{name[:-4]}.png")).convert("RGB"),
                      np.float32)


MID_BAND = (200, 228, 252)
bands = np.zeros((100, 250, 3), np.uint8)
bands[:, :62], bands[:, 62:188], bands[:, 188:] = (250, 200, 200), MID_BAND, (200, 250, 200)
pg = paper_with("bands.png", Image.fromarray(bands))
for edge in (pg[:, :8], pg[:, -8:], pg):
    med = np.median(edge.reshape(-1, 3), axis=0)
    assert np.all(np.abs(med - MID_BAND) < 8), f"{med} is not the middle band: not a cover fit"

# a phone stores a portrait photo sideways with an EXIF turn; the sheet must come out upright
up = np.zeros((140, 100, 3), np.uint8)
up[:70], up[70:] = (250, 215, 215), (215, 215, 250)
side = Image.fromarray(up).rotate(90, expand=True)
exif = Image.Exif()
exif[0x0112] = 6                                                  # "turn 90 cw to view"
side.info["exif"] = exif.tobytes()
pg = paper_with("phone.jpg", side)
top, bot = np.median(pg[:20].reshape(-1, 3), 0), np.median(pg[-20:].reshape(-1, 3), 0)
assert top[0] > top[2] + 20 and bot[2] > bot[0] + 20, f"sheet not turned upright: {top} {bot}"

# a transparent PNG is blank paper, not black
pg = paper_with("clear.png", Image.new("RGBA", (60, 80), (0, 0, 0, 0)))
assert np.median(pg) > 240, f"transparent paper came out {np.median(pg):.0f}, should be white"
r = subprocess.run([sys.executable, os.path.join(HERE, "hyperwrite.py"), "--text", "x",
                    "--out", os.path.join(TMP, "t16-bad.png"), "--paper-image",
                    os.path.join(TMP, "t16.txt")], capture_output=True, text=True)
assert r.returncode != 0 and "not a readable image" in r.stderr, r.stderr[-300:]
print("ok")
