"""Smoke test: every output mode renders, with the size and page count it claims.

Added 2026-09-24 with Markdown documents, Photo mode and ZIP export. Each case asserts what a
caller relies on: A4 at 110 dpi is 909 x 1286 px, a PDF has the pages the renderer reported, a
photo is a 3:4 crop with writing on the sheet, a ZIP holds one PNG per page.
"""
import io, json, subprocess, sys, zipfile
import numpy as np
from PIL import Image
from pypdf import PdfReader

H, T = sys.argv[1], sys.argv[2]
doc = ["# Smoke test", "", "- a bullet with $x^2$ inline", "1. a numbered item", "",
       "| a | b |", "|---|---|", "| 1 | 2 |", "", "$$\\frac{a+b}{\\sqrt{c}}$$", "",
       "Привет, мир. Ελληνικά. 你好世界。", ""]
doc += [f"Paragraph {i} runs long enough to wrap across the page at least once or twice." for i in range(60)]
open(f"{T}/doc.md", "w").write("\n".join(doc))


def run(*args):
    r = subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/doc.md",
                        "--seed", "4", "--dpi", "110", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout)


def dims(mm, dpi=110):
    return int(mm[0] * dpi / 25.4), int(mm[1] * dpi / 25.4)


# print mode, multi-page PDF
rep = run("--out", f"{T}/doc.pdf", "--paper", "college")
n = len(PdfReader(f"{T}/doc.pdf").pages)
assert n == rep["pages"] >= 2, f"PDF has {n} pages, renderer said {rep['pages']}"
assert tuple(rep["size_px"]) == dims((210, 297)), rep["size_px"]

# PNG pages, every paper in the catalog renders one page at the right size
for paper in ("squared5", "lineatur27", "india", "plain", "dotted"):
    rep = run("--out", f"{T}/{paper}.png", "--paper", paper, "--max-pages", "1")
    im = Image.open(f"{T}/{paper}.png")
    assert im.size == dims((210, 297)), f"{paper}: {im.size}"

# landscape letter, JPG
rep = run("--out", f"{T}/l.jpg", "--pagesize", "letter", "--landscape", "--max-pages", "1")
assert Image.open(f"{T}/l.jpg").size == dims((279.4, 215.9)), Image.open(f"{T}/l.jpg").size

# ZIP of PNG pages
rep = run("--out", f"{T}/doc.zip", "--max-pages", "3")
names = zipfile.ZipFile(f"{T}/doc.zip").namelist()
assert len(names) == rep["pages"] == 3 and all(x.endswith(".png") for x in names), names

# photo mode: a generated plate, and the offline fallback
for scene in ("oak-mug", "fallback"):
    rep = run("--out", f"{T}/ph-{scene}.jpg", "--mode", "photo", "--scene", scene,
              "--view", "closer", "--max-pages", "1")
    im = Image.open(f"{T}/ph-{scene}.jpg").convert("L")
    w, h = im.size
    assert abs(w / h - 0.75) < 0.03, f"{scene}: photo is {w}x{h}, not 3:4"
    a = np.asarray(im, np.float32)
    mid = a[int(h * 0.25):int(h * 0.6), int(w * 0.25):int(w * 0.75)]
    assert (mid < 110).mean() > 0.002, f"{scene}: no writing on the sheet"
    assert rep["scene"] == [scene], rep["scene"]
print("ok")
