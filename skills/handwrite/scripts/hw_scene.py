#!/usr/bin/env python3
"""
hw_scene — Photo mode: the written page, photographed lying on a desk.

handtextai's Photo mode writes onto photographs of real notebooks (`paper-templates/*_scene.jpg`,
8 plates, all PRO). Those photos are theirs. Ours are generated: an image model draws a desk
with ONE BLANK UNRULED SHEET on it, the sheet's four corners are found automatically, and the
rendered page (paper, ruling and ink) is warped onto that sheet and MULTIPLIED by the photo's
own light. So the shadows, the window gradient and the paper's curl in the photo land on the
writing too, which is what makes it read as a photo rather than a page pasted on a picture.

    python3 scripts/hw_scene.py plates --budget 2.0      # generate the library (once)
    python3 scripts/hw_scene.py list
    python3 scripts/hw_scene.py detect oak-mug           # re-find the sheet corners
    python3 scripts/hyperwrite.py --file notes.md --out photo.jpg --mode photo --scene oak-mug

Every plate's model, prompt, date and cost is in assets/scenes/manifest.json.
"""
import argparse, base64, datetime, io, json, math, os, random, sys, urllib.request
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCENES = os.path.join(ROOT, "assets", "scenes")
MANIFEST = os.path.join(SCENES, "manifest.json")
MODEL = "google/gemini-3-pro-image"

BASE = ("A realistic smartphone photograph of ONE blank sheet of plain white paper with NO lines, "
        "NO grid, NO margin line and NO writing, lying flat. All four corners of the sheet are "
        "fully visible and nothing covers the sheet. The sheet fills about 60 percent of the "
        "frame, portrait orientation. No text, no logos, no people, no hands. ")
PLATES = {
    "oak-mug": "Shot from directly above on a warm oak wooden desk. A black ballpoint pen lies "
               "beside the sheet and a white coffee mug sits in the top right corner. Soft window "
               "light from the left, gentle realistic shadows, slight vignette.",
    "dark-desk": "Shot from directly above on a matte black desk. A graphite pencil and a "
                 "smartphone lie beside the sheet. Cool daylight, crisp soft shadows.",
    "marble": "Shot from directly above on white-grey marble. A gold pen and a small eucalyptus "
              "sprig lie beside the sheet. Bright airy light.",
    "study-desk": "Shot from directly above on a light wooden student desk with the corner of a "
                  "closed laptop, two highlighters and a closed textbook with a plain cover around "
                  "the sheet. Overhead room light.",
    "lamp-angle": "Shot at a slight angle, about 20 degrees from vertical, so the sheet shows gentle "
                  "perspective, on a walnut table in the evening under a warm desk lamp from the "
                  "upper right, warm pools of light and soft falloff.",
    "window-shadow": "Shot from directly above on a pale linen tablecloth in afternoon sun, with "
                     "soft shadows of a window frame falling diagonally across part of the sheet "
                     "and the table.",
    "clipboard": "The sheet is held on a brown hardboard clipboard with a metal clip at the top, "
                 "the clipboard lying on a grey sofa cushion, shot from above in soft daylight.",
    "concrete": "Shot from directly above on a light grey concrete surface with a black fineliner "
                "and a pair of glasses beside the sheet. Even overcast daylight.",
}


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k
    p = os.path.expanduser("~/.env.master")
    if os.path.exists(p):
        for ln in open(p):
            if ln.strip().startswith(("OPENROUTER_API_KEY=", "export OPENROUTER_API_KEY=")):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def manifest():
    if os.path.exists(MANIFEST):
        return json.load(open(MANIFEST))
    return {"plates": {}, "spent_usd": 0.0}


def save_manifest(m):
    os.makedirs(SCENES, exist_ok=True)
    json.dump(m, open(MANIFEST, "w"), indent=2)


def generate(name, prompt, key, model=MODEL):
    body = json.dumps({"model": model, "modalities": ["image", "text"],
                       "image_config": {"aspect_ratio": "3:4", "image_size": "2K"},
                       "messages": [{"role": "user", "content": prompt}],
                       "usage": {"include": True}}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json",
                                  "X-Title": "hyperwrite-scenes"})
    with urllib.request.urlopen(req, timeout=600) as r:
        j = json.load(r)
    msg = j["choices"][0]["message"]
    if not msg.get("images"):
        raise RuntimeError("no image returned: " + (msg.get("content") or "")[:200])
    raw = base64.b64decode(msg["images"][0]["image_url"]["url"].split(",", 1)[1])
    return Image.open(io.BytesIO(raw)).convert("RGB"), float(j.get("usage", {}).get("cost") or 0)


# ------------------------------------------------------------------ finding the sheet
def _components(mask, min_frac):
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = []
    for sy in range(0, h, 3):
        for sx in range(0, w, 3):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            comp, q = [], deque([(sy, sx)])
            seen[sy, sx] = True
            while q:
                y, x = q.popleft()
                comp.append((y, x))
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(comp) >= h * w * min_frac:
                out.append(comp)
    return out


def _corners(pts):
    s, d = pts.sum(1), pts[:, 0] - pts[:, 1]
    return [pts[s.argmin()], pts[d.argmax()], pts[s.argmax()], pts[d.argmin()]]


def _area(q):
    return 0.5 * abs(sum(q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1] for i in range(4)))


def detect_quad(img):
    """Four corners of the blank sheet, (TL, TR, BR, BL) in plate pixels.

    The sheet is a bright, colourless region SHAPED LIKE A QUADRILATERAL. Brightness alone is
    not enough: a sunlit linen cloth or a lamp-lit table is as bright as paper and merges with
    it into one blob. So several thresholds are tried and the component that best fills the
    quad through its own diagonal extremes wins — a merged blob never fills its quad."""
    small = img.copy()
    small.thumbnail((360, 360))
    k = img.width / small.width
    a = np.asarray(small, np.float32) / 255.0
    lum = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    h, w = lum.shape
    best, best_fit = None, 0.0
    for pct in (50, 60, 70, 78, 85):
        for smax in (0.10, 0.16, 0.24):
            thr = max(0.45, float(np.percentile(lum, pct)))
            for comp in _components((lum > thr) & (sat < smax), 0.08):
                pts = np.array(comp, np.float32)[:, ::-1]
                q = _corners(pts)
                fit = len(comp) / max(1.0, _area(q))
                # the LARGEST well-filled region: a high threshold also yields a tidy quad, but
                # it is only the brightest part of the sheet (measured on the concrete plate)
                score = len(comp) / (h * w)
                if fit > 0.93 and score > best_fit:
                    best, best_fit = (pts, q), score
    if best is None:
        raise RuntimeError("no sheet-shaped region found in the plate")
    pts, q = best
    # the extreme pixel CENTRES of a thumbnail sit up to a pixel inside the true edge; push
    # each corner out along its diagonal or a sliver of the plate's own sheet shows round it
    c = pts.mean(0)
    out = []
    for p in q:
        v = p - c
        p = p + v / (np.linalg.norm(v) + 1e-6) * 1.6
        out.append([float(p[0] * k), float(p[1] * k)])
    return out


def _homography(src, dst):
    """3x3 H with dst ~ H @ src, from four point pairs."""
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    hvec = np.linalg.solve(np.array(A, np.float64), np.array(b, np.float64))
    return np.append(hvec, 1.0).reshape(3, 3)


def _inset(quad, f):
    c = np.mean(quad, axis=0)
    return [list(c + (np.array(p) - c) * (1 - f)) for p in quad]


# ------------------------------------------------------------------ compositing
def composite(page, plate, quad, rng):
    """Warp `page` onto the sheet at `quad` and light it with the plate's own light."""
    W, H = plate.size
    q = _inset(quad, 0.0015)
    pw, ph = page.size
    # PIL's PERSPECTIVE wants the map FROM output (plate) TO input (page)
    Hm = _homography(q, [(0, 0), (pw, 0), (pw, ph), (0, ph)])
    coeffs = (Hm / Hm[2, 2]).flatten()[:8]
    warped = page.convert("RGB").transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = Image.new("L", page.size, 255).transform((W, H), Image.PERSPECTIVE, coeffs,
                                                     Image.BILINEAR)
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))
    pl = np.asarray(plate, np.float32) / 255.0
    m = np.asarray(mask, np.float32)[..., None] / 255.0
    # the plate's sheet, divided by its own white, IS the light falling on the page
    inside = m[..., 0] > 0.9
    white = np.percentile(pl[inside], 97, axis=0) if inside.any() else np.ones(3, np.float32)
    light = np.clip(pl / np.maximum(white, 1e-3), 0, 1.15)
    light = np.asarray(Image.fromarray((np.clip(light / 1.15, 0, 1) * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0 * 1.15
    wp = np.asarray(warped, np.float32) / 255.0
    # a phone lens is softer than a scanner: take the edge off the ink at the plate's scale
    scale = math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) / pw
    if scale < 0.9:
        wp = np.asarray(Image.fromarray((wp * 255).astype(np.uint8))
                        .filter(ImageFilter.GaussianBlur(0.45)), np.float32) / 255.0
    lit = wp * light
    lit = lit + rng.normal(0, 0.012, lit.shape).astype(np.float32)
    out = pl * (1 - m) + np.clip(lit, 0, 1) * m
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def frame(img, quad, view):
    """wide = the whole photo; closer and closest crop in on the sheet, keeping 3:4."""
    if view == "wide":
        return img
    W, H = img.size
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    pad = 0.16 if view == "closer" else 0.035
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    bw, bh = (max(xs) - min(xs)) * (1 + 2 * pad), (max(ys) - min(ys)) * (1 + 2 * pad)
    if bw / bh > 0.75:
        bh = bw / 0.75
    else:
        bw = bh * 0.75
    x0 = max(0, min(W - bw, cx - bw / 2)); y0 = max(0, min(H - bh, cy - bh / 2))
    return img.crop((int(x0), int(y0), int(min(W, x0 + bw)), int(min(H, y0 + bh))))


def fallback_plate(rng, page_aspect):
    """No generated plates yet: a plain desk colour with a soft shadow, so --mode photo still
    works offline. It is honest about being a fallback in the report."""
    W, H = 1800, 2400
    tone = np.array(rng.choice([(118, 88, 60), (60, 62, 66), (205, 200, 192)]), np.float32) / 255
    base = np.ones((H, W, 3), np.float32) * tone
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base *= (1.08 - 0.25 * np.hypot(xx / W - 0.3, yy / H - 0.2))[..., None]
    pw = W * 0.62
    ph = pw / page_aspect
    x0, y0 = (W - pw) / 2 + rng.uniform(-40, 40), (H - ph) / 2 + rng.uniform(-40, 40)
    rot = math.radians(rng.uniform(-3, 3))
    c = np.array([x0 + pw / 2, y0 + ph / 2])
    corners = [(x0, y0), (x0 + pw, y0), (x0 + pw, y0 + ph), (x0, y0 + ph)]
    quad = [list(c + np.array([[math.cos(rot), -math.sin(rot)], [math.sin(rot), math.cos(rot)]])
                 @ (np.array(p) - c)) for p in corners]
    sh = Image.new("L", (W, H), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(sh).polygon([(x + 18, y + 26) for x, y in quad], fill=150)
    sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(28)), np.float32)[..., None] / 255.0
    base = base * (1 - sh * 0.55)
    sheet = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sheet).polygon([tuple(p) for p in quad], fill=255)
    s = np.asarray(sheet, np.float32)[..., None] / 255.0
    base = base * (1 - s) + np.array([0.97, 0.965, 0.95], np.float32) * s
    img = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))
    return img, quad


def place_pages(pages, scene, view, seed, dpi):
    """Put every page into a scene. Returns (images, [scene names used])."""
    m = manifest()
    names = sorted(n for n, p in m["plates"].items()
                   if p.get("quad") and os.path.exists(os.path.join(SCENES, p["file"])))
    rng = random.Random(seed)
    nrng = np.random.RandomState(seed & 0x7FFFFFFF)
    out, used = [], []
    for i, page in enumerate(pages):
        if names and scene != "fallback":
            name = rng.choice(names) if scene == "random" else scene
            if name not in m["plates"]:
                sys.exit(f"no scene {name!r}; have {', '.join(names)} (or random)")
            rec = m["plates"][name]
            plate = Image.open(os.path.join(SCENES, rec["file"])).convert("RGB")
            quad = rec["quad"]
        else:
            name = "fallback"
            plate, quad = fallback_plate(rng, page.width / page.height)
        img = composite(page, plate, quad, nrng)
        out.append(frame(img, quad, view))
        used.append(name)
    return out, used


def main():
    ap = argparse.ArgumentParser(description="photo-mode scene plates")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("plates", help="generate missing plates")
    g.add_argument("--only", nargs="*")
    g.add_argument("--budget", type=float, default=2.0, help="stop before spending more, USD")
    g.add_argument("--model", default=MODEL)
    d = sub.add_parser("detect")
    d.add_argument("name")
    sub.add_parser("list")
    o = sub.add_parser("overlay", help="every plate with its sheet outline, to check by eye")
    o.add_argument("--out", required=True)
    a = ap.parse_args()
    m = manifest()
    if a.cmd == "list":
        for n, p in sorted(m["plates"].items()):
            print(f"{n:14} ${p['cost_usd']:.4f}  {p['model']}  {p['date']}")
        print(f"total spent: ${m.get('spent_usd', 0):.4f}")
        return
    if a.cmd == "overlay":
        from PIL import ImageDraw
        tiles = []
        for n, rec in sorted(m["plates"].items()):
            im = Image.open(os.path.join(SCENES, rec["file"])).convert("RGB")
            if rec.get("quad"):
                q = [tuple(p) for p in rec["quad"]]
                ImageDraw.Draw(im).line(q + [q[0]], fill=(255, 0, 0), width=8)
            im.thumbnail((450, 600))
            tiles.append(im)
        cols = 4
        S = Image.new("RGB", (450 * cols, 600 * math.ceil(len(tiles) / cols)), "white")
        for i, t in enumerate(tiles):
            S.paste(t, ((i % cols) * 450, (i // cols) * 600))
        S.save(a.out)
        print(a.out)
        return
    if a.cmd == "detect":
        rec = m["plates"][a.name]
        rec["quad_source"] = "detect_quad"
        rec["quad"] = detect_quad(Image.open(os.path.join(SCENES, rec["file"])).convert("RGB"))
        save_manifest(m)
        print(json.dumps(rec["quad"]))
        return
    key = load_key()
    if not key:
        sys.exit("no OPENROUTER_API_KEY (env or ~/.env.master)")
    spent = 0.0
    for name, extra in PLATES.items():
        if a.only and name not in a.only:
            continue
        if name in m["plates"]:
            continue
        if spent + 0.15 > a.budget:
            print(f"budget reached at ${spent:.4f}; stopping before {name}")
            break
        prompt = BASE + extra
        img, cost = generate(name, prompt, key, a.model)
        spent += cost
        m["spent_usd"] = round(m.get("spent_usd", 0.0) + cost, 5)
        fn = f"{name}.jpg"
        os.makedirs(SCENES, exist_ok=True)
        img.save(os.path.join(SCENES, fn), quality=90)
        try:
            quad = detect_quad(img)
            top = math.dist(quad[0], quad[1]); side = math.dist(quad[1], quad[2])
            if not 0.55 < top / max(side, 1) < 0.85:
                print(f"{name}: sheet outline is {top / max(side, 1):.2f} wide per unit tall, "
                      f"not paper-shaped; check it with `overlay` and set the quad by hand")
        except RuntimeError as e:
            print(f"{name}: {e}; kept for inspection, not usable until `detect` succeeds")
            quad = None
        m["plates"][name] = {"file": fn, "model": a.model, "prompt": prompt,
                             "date": datetime.date.today().isoformat(),
                             "cost_usd": round(cost, 5), "size": list(img.size), "quad": quad,
                             "rights": "generated for this skill; no third-party photo used"}
        save_manifest(m)
        print(f"{name}: ${cost:.4f}  quad={'ok' if quad else 'none'}")
    print(f"spent this run ${spent:.4f}; library total ${m.get('spent_usd', 0):.4f}")


if __name__ == "__main__":
    main()
