#!/usr/bin/env python3
"""
judge — score how convincingly a page image reads as handwritten.

Two independent lanes, because either one alone is gameable:

  FORENSIC   five deterministic measurements that a font-rendered page fails and a real
             photographed page passes. Free, instant, no network, and it works on ANY page
             image — so you can point it at a competitor's output and get a comparable number.
  PANEL      a panel of vision models on OpenRouter, each asked the only question that
             matters: is this handwritten or generated, and what gave it away.

The forensic score is the loop's exit condition (cheap, deterministic, no rate limit).
The panel is the calibration — run it occasionally to confirm the forensic score still
tracks what a human sees.
"""
import argparse, base64, io, json, os, re, sys, math, concurrent.futures as cf

import numpy as np
from PIL import Image, ImageFilter

# ---------------------------------------------------------------- forensic lane
def ink_mask(img):
    a = np.asarray(img.convert("L"), np.float32) / 255.0
    # paper is the bright mode; ink is everything meaningfully darker than local paper
    bg = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(24)), np.float32) / 255.0
    d = np.clip(bg - a, 0, 1)
    thr = max(0.08, float(np.percentile(d, 99.0)) * 0.30)
    return d, (d > thr)

def label_components(mask, max_iter=140):
    """Connected components by label propagation. scipy would do this in one call; we avoid
    the dependency because this script has to run anywhere, including inside a judge loop."""
    h, w = mask.shape
    lab = np.where(mask, np.arange(h * w, dtype=np.int32).reshape(h, w), -1)
    for _ in range(max_iter):
        prev = lab
        m = lab.copy()
        m[:-1, :] = np.maximum(m[:-1, :], lab[1:, :])
        m[1:, :]  = np.maximum(m[1:, :],  lab[:-1, :])
        m[:, :-1] = np.maximum(m[:, :-1], lab[:, 1:])
        m[:, 1:]  = np.maximum(m[:, 1:],  lab[:, :-1])
        lab = np.where(mask, m, -1)
        if np.array_equal(lab, prev):
            break
    return lab

def blob_floor(mask):
    """Smallest ink blob worth calling a letter, in DOWNSAMPLED pixels, derived from how big
    the writing on this page actually is.

    A fixed floor of 25px was used here and it silently broke: once the engine started fitting
    its writing to the paper's ruling, small hands fell under it and a full page of 250 letters
    measured as 13 merged blobs, which scored as highly unique. Measured 2026-09-21.
    """
    rows = line_rows(mask)
    if len(rows) < 2:
        return 25
    mh = float(np.median([b - a for a, b in rows]))
    return max(8, (mh * mh) / 40.0)

def m_glyph_uniqueness(d, mask):
    """A font draws every `a` from one outline. Crop the ink blobs, normalise them, and see
    how close each one's nearest twin is. A rendered font page is full of 0.97 twins."""
    floor = blob_floor(mask)
    small = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(
        (mask.shape[1] // 2, mask.shape[0] // 2), Image.NEAREST), np.float32) > 127
    lab = label_components(small)
    ids, counts = np.unique(lab[lab >= 0], return_counts=True)
    keep = ids[(counts > floor) & (counts < small.size * 0.02)]
    if len(keep) < 12:
        return None, 0
    crops = []
    for i in keep[:260]:
        ys, xs = np.nonzero(lab == i)
        c = small[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
        if c.shape[0] < 4 or c.shape[1] < 3:
            continue
        ar = c.shape[1] / c.shape[0]
        t = np.asarray(Image.fromarray((c * 255).astype(np.uint8)).resize((24, 24), Image.BILINEAR),
                       np.float32) / 255.0
        t = (t - t.mean()) / (t.std() + 1e-6)
        crops.append((ar, t.ravel()))
    if len(crops) < 12:
        return None, 0
    M = np.stack([c[1] for c in crops])
    ars = np.array([c[0] for c in crops])
    C = (M @ M.T) / M.shape[1]
    np.fill_diagonal(C, -9)
    # only compare shapes of similar proportion — an `l` next to an `m` proves nothing
    same = np.abs(np.log(ars[:, None] / ars[None, :])) < 0.25
    C = np.where(same, C, -9)
    best = C.max(axis=1)
    best = best[best > -8]
    return (float(np.mean(best)) if len(best) else None), len(crops)

def m_ink_flatness(d, mask):
    """Inside a stroke, a flat vector fill has almost no variance. Real ink varies with
    pressure, pooling and the paper grain showing through it."""
    core = np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                      .filter(ImageFilter.MinFilter(3)), np.float32) > 127
    v = d[core]
    if v.size < 200:
        return None
    return float(v.std() / (v.mean() + 1e-6))

def line_rows(mask):
    prof = mask.sum(1).astype(np.float32)
    thr = max(3.0, prof.max() * 0.04)
    runs, on = [], False
    for y, p in enumerate(prof):
        if p > thr and not on:
            on, s = True, y
        elif p <= thr and on:
            on = False
            if y - s > 4:
                runs.append((s, y))
    if on:
        runs.append((s, len(prof)))
    return runs

def m_baseline_wander(d, mask):
    """The property that separates writing from a ransom note is not the SIZE of the error,
    it is its CORRELATION. Detrend each line's baseline, then measure how far it wanders AND
    whether consecutive samples agree. A font scores ~0 (no wander). Uniform per-glyph jitter
    also scores ~0 (wander, but each sample disagrees with the last). Only a hand scores high.

    A spectral low/high energy ratio was tried first and does NOT discriminate: on a perfectly
    straight baseline the residual is rounding noise, and the ratio of two tiny numbers is
    meaningless. Amplitude x autocorrelation is the honest version.
    """
    out = []
    rows = line_rows(mask)
    if len(rows) < 3:
        return None
    gaps = np.diff([(a + b) / 2 for a, b in rows])
    gap = float(np.median(gaps)) if len(gaps) else 1.0
    if gap <= 1:
        return None
    for (a, b) in rows[:30]:
        band = mask[a:b]
        cols = np.nonzero(band.sum(0) > 0)[0]
        if len(cols) < 150:
            continue
        raw = np.array([np.nonzero(band[:, x])[0].max() for x in cols], np.float32)
        # bin and take the median: the lowest ink in a column is a descender as often as
        # it is the baseline, and descenders are content, not handwriting behaviour
        nb = max(10, len(cols) // 22)
        e = np.linspace(0, len(cols), nb + 1).astype(int)
        ys = np.array([np.median(raw[e[i]:e[i + 1]]) for i in range(nb) if e[i + 1] > e[i]],
                      np.float32)
        if len(ys) < 8:
            continue
        t = np.arange(len(ys), dtype=np.float32)
        res = ys - np.polyval(np.polyfit(t, ys, 1), t)
        amp = float(res.std()) / gap
        if res.std() < 1e-6:
            out.append(0.0); continue
        r0, r1 = res[:-1], res[1:]
        ac = float(np.corrcoef(r0, r1)[0, 1]) if r0.std() > 1e-9 and r1.std() > 1e-9 else 0.0
        out.append(amp * max(0.0, ac))
    return float(np.mean(out)) if out else None

def m_line_start_scatter(d, mask, page_w):
    starts = []
    for (a, b) in line_rows(mask):
        cols = np.nonzero(mask[a:b].sum(0) > 0)[0]
        if len(cols):
            starts.append(cols[0])
    if len(starts) < 5:
        return None
    return float(np.std(starts) / page_w)

def m_paper_life(img):
    """Paper is never one flat colour. Measure the texture energy of the page away from ink."""
    a = np.asarray(img.convert("L"), np.float32) / 255.0
    _, mask = ink_mask(img)
    far = ~np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                      .filter(ImageFilter.MaxFilter(9)), np.float32).astype(bool)
    hp = a - np.asarray(Image.fromarray((a * 255).astype(np.uint8))
                        .filter(ImageFilter.GaussianBlur(3)), np.float32) / 255.0
    v = hp[far]
    return float(v.std()) if v.size > 1000 else None


LEGIBILITY_MODEL = "google/gemini-3-flash-preview"

def _read_back(path, key, model=LEGIBILITY_MODEL, max_px=1500):
    """Ask a vision model to simply READ the page. Cheap (about $0.001), and it is the only
    thing that works here.

    tesseract was tried first and discarded, measured 2026-09-21: it scores 0.77 on a clean
    font page and 0.01 on BOTH a perfectly legible handwritten page and an illegible one. It
    is trained on print, so it cannot tell good handwriting from mush — it fails them equally.
    """
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_px:
        sc = max_px / max(img.size)
        img = img.resize((int(img.width * sc), int(img.height * sc)), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    import urllib.request
    body = json.dumps({
        "model": model, "provider": {"allow_fallbacks": False},
        "reasoning": {"enabled": False}, "max_tokens": 1400,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Transcribe this page exactly as written. Output only the "
             "transcription, no commentary. If a word is unreadable write [?]."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json",
                                  "X-Title": "hyperwrite-legibility"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def m_legibility(path, reference, key):
    """Can it still be READ?

    A realism score on its own is gameable, and the exploit is letter collision: merge
    neighbouring glyphs and `glyph_uniqueness` and `ink_flatness` both improve while the page
    stops being readable. Measured 2026-09-21 — a tuning loop found that exploit in 47 renders
    and scored 82.8/100 on a page nobody can read. Geometry does not catch it either (the
    merged blobs' width/height was 0.92, LOWER than a real hand's 1.14 — tried and discarded).

    So the gate is: read it back and diff. Returns 0..1, and None when it could not be checked,
    which never fails the gate — a missing check is not a pass, it is an absent measurement.
    """
    if not reference or not key:
        return None
    try:
        got = _read_back(path, key)
    except Exception:
        return None
    import difflib, re as _re
    norm = lambda t: _re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    a, b = norm(reference), norm(got)
    if not b:
        return 0.0
    a = a[:max(240, int(len(b) * 1.35))]
    return float(difflib.SequenceMatcher(None, a, b).ratio())

COLLISION_MAX = 0.06   # adjacent-glyph overlap rate above which a page reads as mush

BANDS = {
    # metric: (fail_anchor, pass_anchor, weight)
    #
    # Both anchors are MEASURED, not guessed (2026-09-21, scripts/calibrate.sh):
    #   fail = a pure font page — one outline per letter, no physics, clean render
    #   pass = a real pen-on-paper page photographed with a phone
    # Do not hand-tune these. Re-run the calibration and paste what it prints.
    # Weights follow MEASURED reliability, not intuition. Coefficient of variation over
    # five seeds of the same settings (2026-09-21, scripts/calibrate.sh):
    #   glyph_uniqueness 0.03 | ink_flatness 0.07 | paper_life 0.10
    #   baseline_wander  0.31 | line_start_px 0.80  <- mostly noise, weighted near zero
    # A metric that moves 80% between seeds cannot carry a tuning decision.
    "glyph_uniqueness": (0.946, 0.400, 0.38),   # font 0.946 | real hand 0.312   cv 0.03
    "ink_flatness":     (0.026, 0.087, 0.27),   # font 0.025 | real hand 0.087   cv 0.07
    "paper_life":       (0.004, 0.013, 0.17),   # font 0.013 | real hand 0.013   cv 0.10
    "baseline_wander":  (0.004, 0.055, 0.14),   # font 0.016 | real hand 0.055   cv 0.31
    "line_start_px":    (0.005, 0.030, 0.04),   # font 0.019 | ruled target      cv 0.80
}

# What a competitor scores on the same scale, for reference only — never a target.
REFERENCE = {"handtextai.com (site preview, 2026-09-21)": 70.3}

def forensic(path, reference=None, key=None):
    img = Image.open(path).convert("RGB")
    d, mask = ink_mask(img)
    gu, n = m_glyph_uniqueness(d, mask)
    vals = {
        "glyph_uniqueness": gu,
        "ink_flatness":     m_ink_flatness(d, mask),
        "baseline_wander":  m_baseline_wander(d, mask),
        "line_start_px":    m_line_start_scatter(d, mask, img.width),
        "paper_life":       m_paper_life(img),
    }
    # the renderer's own sidecar is the legibility gate when it exists — exact, free,
    # and unlike OCR or a vision read-back it cannot be fooled by a model guessing the words
    side = os.path.splitext(path)[0].rsplit("-", 1)[0] + ".hyperwrite.json"
    collision = None
    for cand in (os.path.splitext(path)[0] + ".hyperwrite.json", side):
        if os.path.exists(cand):
            try:
                collision = json.load(open(cand)).get("collision_rate")
                break
            except (OSError, ValueError):
                pass
    legibility = m_legibility(path, reference, key) if reference else None
    parts, total_w = {}, 0.0
    score = 0.0
    for k, v in vals.items():
        fail, good, w = BANDS[k]
        if v is None:
            parts[k] = None
            continue
        t = (v - fail) / (good - fail)
        t = max(0.0, min(1.0, t))
        parts[k] = round(t, 3)
        score += t * w
        total_w += w
    raw_score = 100 * score / max(total_w, 1e-6)
    # The gate: an unreadable page is not a realistic page, whatever the metrics say.
    legible = collision is None or collision <= COLLISION_MAX
    if not legible:
        raw_score = raw_score * max(0.0, 1.0 - (collision - COLLISION_MAX) * 9.0)
    return {
        "file": os.path.basename(path),
        "glyphs_measured": n,
        "collision_rate": collision,
        "read_back": round(legibility, 3) if legibility is not None else None,
        "legible": legible,
        "raw": {k: (round(v, 5) if v is not None else None) for k, v in vals.items()},
        "normalised": parts,
        "forensic_score": round(raw_score, 1),
    }

def match(page, reference, key=None):
    """How close is this render to THAT page?

    The forensic score answers "does this read as handwritten at all", against fixed anchors.
    This answers a different question: given a photo of a specific real page, how near is the
    render to it on each measurable axis. Per-metric distance is normalised by that metric's
    own band width, so a miss on ink variation and a miss on baseline wander are comparable.

    It cannot see LETTERFORMS, which is the axis it would most like to see. `glyph_uniqueness`
    tells you whether the render varies its letters as much as the reference does, not whether
    they are the same shapes. A render can match on every number here and still be visibly a
    different hand — say so rather than reporting the number alone.
    """
    a, b = forensic(page, key=key), forensic(reference, key=key)
    rows, dists = {}, []
    for k, (fail, good, w) in BANDS.items():
        va, vb = a["raw"][k], b["raw"][k]
        if va is None or vb is None:
            rows[k] = None
            continue
        span = abs(good - fail) or 1.0
        d = abs(va - vb) / span
        rows[k] = {"render": va, "reference": vb, "off_by_bands": round(d, 3),
                   "weight": w}
        dists.append(d * w)
    tw = sum(r["weight"] for r in rows.values() if r)
    score = 100 * max(0.0, 1.0 - (sum(dists) / tw if tw else 1.0))
    return {"page": os.path.basename(page), "reference": os.path.basename(reference),
            "match_score": round(score, 1), "metrics": rows,
            "render_forensic": a["forensic_score"], "reference_forensic": b["forensic_score"],
            "caveat": "measures behaviour, not letterforms — a perfect score can still be a "
                      "different hand"}

# ---------------------------------------------------------------- panel lane
PANEL = ["google/gemini-3-flash-preview", "qwen/qwen3-vl-235b-a22b-instruct"]
STRICT = PANEL + ["anthropic/claude-opus-5"]

PROMPT = """You are shown one page. Decide whether a human wrote it by hand on physical paper,
or whether it was produced by software.

Answer ONLY with JSON:
{"verdict":"handwritten"|"generated"|"unsure",
 "confidence":0-100,
 "realism":0-100,
 "tells":["the specific things that gave it away, most damning first"],
 "next_fix":"the single change that would most improve it"}

Judge these specifically, and say so in `tells` when one fails:
- do repeated letters differ from each other, or is every `a` identical?
- does the baseline wander on a slow curve, or does each letter jitter independently?
- does the ink vary in darkness along a stroke, and pool where the pen slowed?
- can you see paper grain through the ink?
- do line starts and word gaps scatter the way a hand does?
- does the writing degrade down the page as the hand tires?
- does the capture look like a photo or scan of paper, or like a clean render?"""

def ask(model, b64, key, timeout=120):
    import urllib.request
    body = json.dumps({
        "model": model,
        "provider": {"allow_fallbacks": False},
        "reasoning": {"enabled": False},
        "max_tokens": 700,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json",
                                  "X-Title": "hyperwrite-judge"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.load(r)
        txt = j["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        out = json.loads(m.group(0)) if m else {"raw": txt}
        out["model"] = model
        return out
    except Exception as e:
        return {"model": model, "error": f"{type(e).__name__}: {e}"}

def panel(path, models, key, max_px=1400):
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_px:
        s = max_px / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    with cf.ThreadPoolExecutor(len(models)) as ex:
        res = list(ex.map(lambda m: ask(m, b64, key), models))
    good = [r for r in res if "realism" in r]
    return {
        "votes": res,
        "panel_realism": round(sum(r["realism"] for r in good) / len(good), 1) if good else None,
        "handwritten_votes": sum(1 for r in good if r.get("verdict") == "handwritten"),
        "of": len(good),
        "tells": [t for r in good for t in (r.get("tells") or [])],
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

def main():
    ap = argparse.ArgumentParser(description="score a page for handwriting realism")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--panel", action="store_true", help="also ask the vision models")
    ap.add_argument("--strict", action="store_true", help="add Opus 5 to the panel")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--text", help="the source text, so OCR can gate legibility")
    ap.add_argument("--reference", help="a photo of a real page: score how close "
                                        "each render is to IT, not to the anchors")
    a = ap.parse_args()
    if a.reference:
        ref = os.path.expanduser(a.reference)
        res = [match(p, ref, load_key()) for p in a.images]
        if a.json:
            print(json.dumps(res, indent=2)); return
        for r in res:
            print(f"\n{r['page']}  vs  {r['reference']}   match {r['match_score']}/100"
                  f"   (forensic {r['render_forensic']} vs {r['reference_forensic']})")
            for k, m in r["metrics"].items():
                if m is None:
                    print(f"   {k:<18} n/a"); continue
                bar = "#" * max(0, int(24 - min(24, m["off_by_bands"] * 24)))
                print(f"   {k:<18} {m['render']:<9.4f} vs {m['reference']:<9.4f} "
                      f"{bar:<24} off by {m['off_by_bands']} bands")
            print(f"   {r['caveat']}")
        return
    out = []
    for p in a.images:
        ref = open(os.path.expanduser(a.text)).read() if a.text and os.path.exists(
            os.path.expanduser(a.text)) else a.text
        r = forensic(p, ref, load_key())
        if a.panel or a.strict:
            key = load_key()
            if not key:
                r["panel"] = {"error": "no OPENROUTER_API_KEY"}
            else:
                r["panel"] = panel(p, STRICT if a.strict else PANEL, key)
        out.append(r)
    if a.json:
        print(json.dumps(out, indent=2)); return
    for r in out:
        cr = r["collision_rate"]
        flag = "" if r["legible"] else f"   <- MUSH (collision {cr} > {COLLISION_MAX})"
        crs = "n/a" if cr is None else cr
        print(f"\n{r['file']}   forensic {r['forensic_score']}/100   "
              f"({r['glyphs_measured']} glyphs, collision {crs}){flag}")
        for k, v in r["normalised"].items():
            raw = r["raw"][k]
            bar = "#" * int((v or 0) * 24)
            print(f"   {k:<18} {str(raw):<10} {bar:<24} {v}")
        if "panel" in r:
            pn = r["panel"]
            if pn.get("error"):
                print(f"   panel: {pn['error']}")
            else:
                print(f"   panel realism {pn['panel_realism']}/100   "
                      f"handwritten {pn['handwritten_votes']}/{pn['of']}")
                for t in dict.fromkeys(pn["tells"]):
                    print(f"     - {t}")

if __name__ == "__main__":
    main()
