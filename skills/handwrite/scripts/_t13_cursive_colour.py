"""Joins must connect letters; a hex ink must actually reach the page.

Cursive is not a font property here — the engine draws the stroke BETWEEN letters, so the
test is that turning it on measurably reduces the number of separate ink components on a
line without pushing glyph collision over the legibility cap.
"""
import sys, subprocess, json
import numpy as np
from PIL import Image, ImageFilter

H, T = sys.argv[1], sys.argv[2]
open(f"{T}/c.txt", "w").write("minimum nonsense wandering along the baseline\n" * 6)

def render(tag, extra):
    r = subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/c.txt",
                        "--out", f"{T}/{tag}.png", "--paper", "blank", "--capture", "print",
                        "--size", "4.4", "--seed", "11", "--dpi", "150", "--max-pages", "1",
                        "--messiness", "0.7"] + extra, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    return json.loads(r.stdout)

def components(path):
    """Count separate blobs of ink. Joins merge letters into words, so this drops sharply.

    Counting ink RUNS per image row was tried first and moved only 3%: a join lives in a thin
    band at the baseline, and every row above it — x-heights, ascenders — is unaffected, so
    the whole-image count drowns the signal.
    """
    sys.path.insert(0, H)
    import judge as J
    im = Image.open(path).convert("RGB")
    d, mask = J.ink_mask(im)
    small = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(
        (mask.shape[1] // 2, mask.shape[0] // 2), Image.NEAREST), np.float32) > 127
    lab = J.label_components(small)
    ids, counts = np.unique(lab[lab >= 0], return_counts=True)
    return int(((counts > 20) & (counts < small.size * 0.05)).sum())

print_ = render("print", ["--cursive", "0"])
curs = render("curs", ["--cursive", "1.0"])
rp, rc = components(f"{T}/print.png"), components(f"{T}/curs.png")
assert rc < rp * 0.80, f"cursive merged only {100*(1-rc/rp):.0f}% of the blobs ({rp} -> {rc})"
assert curs["collision_rate"] <= 0.06, f"cursive collides: {curs['collision_rate']}"

# a hex ink must land on the page, not fall back to a default
hexr = render("hex", ["--ink", "#B03A68", "--cursive", "0"])
a = np.asarray(Image.open(f"{T}/hex.png").convert("RGB"), np.float32)
lum = a.mean(2)
dark = a[lum < np.percentile(lum, 0.5)]
med = dark.mean(axis=0)
assert med[0] > med[2] > med[1], f"ink came out {med.round()} — #B03A68 is red-dominant"
assert hexr["ink"] == "#B03A68"
