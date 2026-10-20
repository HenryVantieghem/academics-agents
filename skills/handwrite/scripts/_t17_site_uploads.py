#!/usr/bin/env python3
"""T17: the site takes your own font and a paper image, and hands back every page as a ZIP.

    python3 _t17_site_uploads.py <scripts dir>

Ported from saurabhdaware/text-to-handwriting on 2026-09-28: font upload (.ttf/.otf), a paper
image as the background, and a download per page. A bad upload must be a 400 with the reason,
not a render that fails later with a stack trace.
"""
import base64, glob, http.client, io, json, os, sys, tempfile, threading, time
import urllib.error, urllib.request, zipfile

import numpy as np
from PIL import Image

HERE = sys.argv[1]
sys.path.insert(0, HERE)
import hw_fonts, serve                                                 # noqa: E402

# a fresh store: the real one lives in the temp folder and outlives runs, so a cached report
# would let this test pass without rendering anything
serve.STORE = tempfile.mkdtemp(prefix="t17-store-")
port = serve.free_port(8960)
srv = serve.Server(("127.0.0.1", port), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
base = f"http://127.0.0.1:{port}"


def post(path, obj):
    r = urllib.request.Request(base + path, json.dumps(obj).encode(),
                               {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def b64(path_or_bytes):
    raw = path_or_bytes if isinstance(path_or_bytes, bytes) else open(path_or_bytes, "rb").read()
    return base64.b64encode(raw).decode()


with urllib.request.urlopen(base + "/", timeout=20) as r:
    html = r.read().decode()
for el in ('id="fontfile"', 'id="paperfile"', 'id="effect"', 'id="zip"', 'data-knob="word_space"',
           'data-knob="letter_spacing"', 'id="margin_top"'):
    assert el in html, f"the page lost its {el} control"
with urllib.request.urlopen(base + "/api/fonts", timeout=20) as r:
    assert json.load(r)["effects"] == ["none", "scanner", "shadows"]

ttf = hw_fonts.resolve("caveat", allow_fetch=False) or next(iter(sorted(
    glob.glob("/System/Library/Fonts/Supplemental/*.ttf") + glob.glob("/usr/share/fonts/**/*.ttf",
                                                                      recursive=True))), None)
assert ttf, "no .ttf on this machine to upload"
sheet = io.BytesIO()
PAPER = (214, 236, 250)
Image.new("RGB", (120, 170), PAPER).save(sheet, "PNG")
general = {"seed": 3, "dpi": 90, "max_pages": 2}
TEXT = "A line in my own font on my own paper."


def page(g):
    return np.asarray(Image.open(os.path.join(serve.STORE, g["generation_id"], g["pages"][0]))
                      .convert("RGB"), np.float32)


st, body = post("/api/generate", {"text": TEXT, "settings": {
    "font": {"upload": {"name": "My Hand.TTF", "data": b64(ttf)}},
    "paper": {"style_id": "blank", "upload": {"name": "sheet.png", "data": b64(sheet.getvalue())}},
    "effects": {"capture": "print"}, "general": general}})
g = json.loads(body)
assert st == 200 and g["pages"], body[:300]
rep = json.load(open(os.path.join(serve.STORE, g["generation_id"], "report.json")))
up = serve.upload_dir()
assert rep["font"].startswith(up) and rep["font"].endswith(".ttf"), rep["font"]
assert rep["paper_image"].startswith(up), rep
mine = page(g)
assert np.all(np.abs(np.median(mine.reshape(-1, 3), 0) - PAPER) < 8), "the paper upload is not the page"
st, body = post("/api/generate", {"text": TEXT, "settings": {
    "paper": {"style_id": "blank", "upload": {"name": "sheet.png", "data": b64(sheet.getvalue())}},
    "effects": {"capture": "print"}, "general": general}})
assert st == 200
assert np.abs(page(json.loads(body)) - mine).mean() > 0.2, "the uploaded font changed nothing"

st, z = post("/api/zip", {"generation_id": g["generation_id"]})
with zipfile.ZipFile(io.BytesIO(z)) as zf:
    names = zf.namelist()
    assert st == 200 and names == [f"page-{i + 1:02d}.png" for i in range(len(g["pages"]))], names
    assert zf.read(names[0])[:8] == b"\x89PNG\r\n\x1a\n"

otf = sorted(glob.glob("/System/Library/Fonts/*.otf") + glob.glob("/Library/Fonts/*.otf"))
if otf:
    st, body = post("/api/generate", {"text": "An OpenType face.", "settings": {
        "font": {"upload": {"name": "face.otf", "data": b64(otf[0])}}, "general": general}})
    assert st == 200, body[:300]
else:
    print("  no .otf on this machine; OpenType upload not exercised", file=sys.stderr)

jpg = io.BytesIO()
Image.new("RGB", (400, 400), (200, 200, 200)).save(jpg, "JPEG")
cut = jpg.getvalue()[: len(jpg.getvalue()) // 2]                 # verify() passes this; load() does not
for settings, why in (
        ({"font": {"upload": {"name": "hand.ttf", "data": b64(b"not a font at all")}}}, "could not be opened"),
        ({"font": {"upload": {"name": "hand.exe", "data": b64(ttf)}}}, "must be one of"),
        ({"font": {"upload": {"name": "hand.ttf", "data": "%%%"}}}, "not valid base64"),
        ({"font": {"upload": {"name": "hand.ttf", "data": 123}}}, "needs a name and base64"),
        ({"paper": {"upload": {"name": "sheet.jpg", "data": b64(cut)}}}, "could not be opened"),
        ({"paper": {"image": "/etc/hosts"}}, "must be uploaded"),
        ({"font": "caveat"}, "must be an object"),
        (["paper"], "must be an object")):
    st, body = post("/api/generate", {"text": "x", "settings": settings})
    assert st == 400 and why in json.loads(body)["error"], (settings, st, body[:200])
assert not [f for f in os.listdir(serve.upload_dir()) if f.endswith(".jpg")], "a bad upload was kept"

c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)       # a body too big to read
c.putrequest("POST", "/api/generate")
c.putheader("Content-Type", "application/json")
c.putheader("Content-Length", str(serve.MAX_BODY + 1))
c.endheaders()
assert c.getresponse().status == 413, "an oversized body was not refused"
srv.shutdown()
print("ok")
