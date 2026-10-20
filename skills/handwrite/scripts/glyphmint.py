#!/usr/bin/env python3
"""
glyphmint — mint a real alphabet from an image model, once, and keep it forever.

The measured ceiling of every font-based handwriting renderer is letterform variety. Warping
one outline gets `glyph_uniqueness` to about 0.62; a real hand sits at 0.31, and the distance
is topology — a person writes an `a` with an open loop, then a closed one, and no amount of
displacement turns one into the other.

Image models are bad at writing a PAGE (they garble text at density, cannot hold one hand for
40 pages, and emit no vector). They are very good at writing an ALPHABET SHEET. So the split
is: the model draws the letters, this engine draws the page.

    glyphmint.py mint --name casual-blue --repeats 3

Three specimen sheets (lowercase, uppercase, digits and punctuation), each holding the set
written out several times by the same hand, are segmented into individually cropped glyphs
with a measured baseline and x-height, and cached under `glyphsets/<name>/`.

Cost, measured 2026-09-21 on OpenRouter: $0.034 a sheet on google/gemini-3.1-flash-lite-image,
so about **$0.10 for a complete hand** with three variants of every character — paid once.
google/gemini-3-pro-image is $0.1375 a sheet and worth it only if the cheap one keeps failing
validation for a style you want.
"""
import argparse, base64, io, json, os, re, sys, urllib.request

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = os.path.join(os.path.dirname(HERE), "glyphsets")

CHEAP = "google/gemini-3.1-flash-lite-image"
GOOD = "google/gemini-3-pro-image"

# Rows are short on purpose. A sheet asked for 26 letters in one line comes back with the
# letters cramped and touching, and touching letters cannot be segmented.
SHEETS = {
    "lower":  ["abcdefg", "hijklmn", "opqrstu", "vwxyz"],
    "upper":  ["ABCDEFG", "HIJKLMN", "OPQRSTU", "VWXYZ"],
    "digits": ["012345", "6789"],
    "punct":  [".,;:", "!?-&"],
}
# letters whose ink sits on the baseline (no descender) — these define the row's baseline
NO_DESCENDER = set("abcdehiklmnorstuvwxzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:!?'\"()-&")
# letters whose height IS the x-height — these define the row's scale
X_HEIGHT = set("acemnorsuvwxz")
# digits are cap-height in most hands, so a digits row divides by CAP_RATIO too
# cap height over x-height in everyday handwriting; measured across the minted sheets
CAP_RATIO = 1.42

def prompt_for(rows, style, ink, repeats):
    block = "\n".join(f"        {'  '.join(r)}" for r in rows)
    body = "\n\n".join([block] * repeats)
    return (
        f"A flat-scanned sheet of plain white unlined paper filling the whole frame, "
        f"photographed straight on under even light.\n\n"
        f"Written on it in {ink} by one adult human in {style}, with WIDE gaps between "
        f"characters and between rows so that no two characters touch anywhere:\n\n"
        f"{body}\n\n"
        f"Write the whole set out {repeats} times, as shown, one group under the other. "
        f"Each time it is written again it is written fresh by the same person, so the same "
        f"character looks slightly different each time — that is wanted.\n\n"
        f"Every character stands alone and is never joined to its neighbour. "
        f"Nothing else appears on the page: no ruled lines, no grid, no margins, no labels, "
        f"no numbering, no decoration, no signature. Plain white paper only."
    )

def call_model(prompt, key, model):
    body = json.dumps({"model": model, "modalities": ["image", "text"],
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json",
                                  "X-Title": "hyperwrite-glyphmint"})
    with urllib.request.urlopen(req, timeout=600) as r:
        j = json.load(r)
    msg = j["choices"][0]["message"]
    imgs = msg.get("images") or []
    if not imgs:
        raise RuntimeError("model returned no image: " + (msg.get("content") or "")[:300])
    raw = base64.b64decode(imgs[0]["image_url"]["url"].split(",", 1)[1])
    return Image.open(io.BytesIO(raw)).convert("RGB"), j.get("usage", {}).get("cost", 0.0)

# ------------------------------------------------------------------ segmentation
def ink_alpha(img):
    """Ink as 0..1 alpha, measured against the local paper rather than a fixed threshold —
    the specimen sheets come back with uneven lighting and a hard threshold eats thin strokes."""
    g = np.asarray(img.convert("L"), np.float32) / 255.0
    bg = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(31)), np.float32) / 255.0
    d = np.clip(bg - g, 0, 1)
    hi = float(np.percentile(d, 99.5))
    if hi < 0.05:
        return None
    return np.clip(d / hi, 0, 1)

def label(mask, max_iter=400):
    h, w = mask.shape
    lab = np.where(mask, np.arange(h * w, dtype=np.int32).reshape(h, w), -1)
    for _ in range(max_iter):
        prev = lab
        m = lab.copy()
        m[:-1, :] = np.maximum(m[:-1, :], lab[1:, :])
        m[1:, :] = np.maximum(m[1:, :], lab[:-1, :])
        m[:, :-1] = np.maximum(m[:, :-1], lab[:, 1:])
        m[:, 1:] = np.maximum(m[:, 1:], lab[:, :-1])
        lab = np.where(mask, m, -1)
        if np.array_equal(lab, prev):
            break
    return lab

def boxes(alpha, min_area):
    lab = label(alpha > 0.30)
    ids, counts = np.unique(lab[lab >= 0], return_counts=True)
    out = []
    for i in ids[counts >= min_area]:
        ys, xs = np.nonzero(lab == i)
        out.append([int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1])
    return out

def attach_dots(bx, small, med_h):
    """Reunite an i/j dot with its stem without letting specks in.

    A dot is: much shorter than a normal glyph, sitting ABOVE another box, and horizontally
    inside that box's span. A speck fails the last two tests almost always. Anything small
    that matches nothing is discarded rather than kept as a glyph.
    """
    keep = [list(b) for b in bx]
    spans = [(b[0], b[1]) for b in keep]
    for s in small:
        if any(s[0] >= b[0] and s[1] <= b[1] and s[2] >= b[2] and s[3] <= b[3] for b in keep):
            continue                                   # already inside a kept box
        if (s[3] - s[2]) > med_h * 0.45:
            continue                                   # too tall to be a dot
        best, bestov = None, 0.0
        for i, (x0, x1) in enumerate(spans):
            ov = min(s[1], x1) - max(s[0], x0)
            narrow = min(s[1] - s[0], x1 - x0)
            if narrow <= 0:
                continue
            frac = ov / narrow
            gap = keep[i][2] - s[3]                    # dot bottom to stem top
            if frac > 0.55 and -2 <= gap < med_h * 0.9 and frac > bestov:
                best, bestov = i, frac
        if best is not None:
            b = keep[best]
            keep[best] = [min(b[0], s[0]), max(b[1], s[1]), min(b[2], s[2]), max(b[3], s[3])]
    return keep

def group_rows(bx, tol):
    """Cluster boxes into text rows by vertical centre."""
    rows, used = [], [False] * len(bx)
    order = sorted(range(len(bx)), key=lambda i: (bx[i][2] + bx[i][3]) / 2)
    for i in order:
        if used[i]:
            continue
        cy = (bx[i][2] + bx[i][3]) / 2
        grp = [j for j in order if not used[j]
               and abs((bx[j][2] + bx[j][3]) / 2 - cy) < tol]
        for j in grp:
            used[j] = True
        rows.append(sorted(grp, key=lambda j: bx[j][0]))
    return rows

def merge_overlapping(bx, idxs, frac=0.30):
    """An `i` is two blobs and a `j` is two blobs; so is a hand-written `=`. Merge any two
    boxes in a row whose x-ranges overlap by more than `frac` of the narrower one."""
    cur = [list(bx[i]) for i in idxs]
    changed = True
    while changed:
        changed = False
        for a in range(len(cur)):
            for b in range(a + 1, len(cur)):
                ax0, ax1, ay0, ay1 = cur[a]
                bx0, bx1, by0, by1 = cur[b]
                ov = min(ax1, bx1) - max(ax0, bx0)
                narrow = min(ax1 - ax0, bx1 - bx0)
                if ov > 0 and narrow > 0 and ov / narrow > frac:
                    cur[a] = [min(ax0, bx0), max(ax1, bx1), min(ay0, by0), max(ay1, by1)]
                    cur.pop(b)
                    changed = True
                    break
            if changed:
                break
    return sorted(cur, key=lambda r: r[0])

def segment(img, rows_expected, repeats):
    """Return {char: [alpha arrays]}; a row whose glyph count does not match what we asked
    for is DROPPED, not guessed at. A mis-assigned glyph poisons every page that uses it."""
    a = ink_alpha(img)
    if a is None:
        return {}, ["sheet has no ink"]
    H, W = a.shape
    # Speck floor stays HIGH. Dropping it to catch the dot on an i admitted stray marks as
    # glyphs of their own, which shifted every row assignment after them and produced a set
    # where `p` was an `h` — measured 2026-09-21, worse than the dotless set it replaced.
    # Dots are reunited by attach_dots() instead, which targets them by shape, not by size.
    bx = boxes(a, min_area=max(24, (H * W) // 120000))
    dots = boxes(a, min_area=max(4, (H * W) // 400000))
    if not bx:
        return {}, ["no components found"]
    med_h = float(np.median([b[3] - b[2] for b in bx]))
    bx = attach_dots(bx, dots, med_h)
    rows = group_rows(bx, tol=med_h * 0.85)
    rows = [r for r in rows if len(r) >= 2]
    want = [s for _ in range(repeats) for s in rows_expected]
    out, notes = {}, []
    if len(rows) != len(want):
        notes.append(f"expected {len(want)} rows, found {len(rows)}")
    for ri, idxs in enumerate(rows):
        if ri >= len(want):
            notes.append(f"row {ri}: extra row, dropped")
            continue
        chars = want[ri]
        merged = merge_overlapping(bx, idxs)
        if len(merged) != len(chars):
            notes.append(f"row {ri} ({chars!r}): {len(merged)} glyphs, expected {len(chars)}")
            continue
        base_src = [m for m, c in zip(merged, chars) if c in NO_DESCENDER]
        baseline = float(np.median([m[3] for m in base_src])) if base_src else \
            float(np.median([m[3] for m in merged]))
        xh_src = [m for m, c in zip(merged, chars) if c in X_HEIGHT]
        if xh_src:
            xh = float(np.median([m[3] - m[2] for m in xh_src]))
        else:
            # No x-height letter in this row (a row of capitals, or of digits). Its median
            # height IS the cap height, so divide it down — storing it directly as the
            # x-height renders every capital at lowercase size, which reads as small caps.
            xh = float(np.median([m[3] - m[2] for m in merged])) / CAP_RATIO
        if xh < 6:
            notes.append(f"row {ri}: x-height {xh:.1f}px too small")
            continue
        for (x0, x1, y0, y1), ch in zip(merged, chars):
            pad = 2
            sub = a[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
            if sub.size < 20:
                continue
            out.setdefault(ch, []).append({
                "alpha": sub,
                # where the baseline sits inside this crop, in units of x-height
                "base_dy": (baseline - (y0 - pad)) / xh,
                "w_xh": sub.shape[1] / xh,
                "h_xh": sub.shape[0] / xh,
            })
    return out, notes

# ------------------------------------------------------------------ store
# Letters only. Digits were minted on the same sheet as the punctuation rows, those rows
# fail validation most of the time, and their stray marks get assigned to whatever row
# validates next — "March 8, 2025" rendered as "March 8,, O, ." Measured 2026-09-21.
# Digits and punctuation fall back to the font, where nobody reads a 7 as handwritten anyway.
# Digits are back, on a sheet of their OWN. They were originally minted beside the
# punctuation rows; those rows fail validation most of the time and their stray marks were
# assigned to whatever row validated next, so "March 8, 2025" rendered as "March 8,, O, .".
# Punctuation still falls back to the font — a comma and a speck are the same shape.
SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

def intra_letter_correlation(glyphs):
    """Mean correlation between the forms stored for the SAME character.

    It reads two ways and both matter:
      ~0.94  the model wrote the alphabet like a font — real, usable, but it will not raise
             glyph_uniqueness on the page, so the engine's warp still has to supply variety
      <0.40  the segmentation MISASSIGNED letters and a `g` is filed under `h`. Measured
             2026-09-21: a prompt pushed toward variability produced a sheet that segmented
             into nonsense and scored 0.077, which looked like a triumph until the contact
             sheet was opened. Reject at this end, never celebrate it.
    """
    import numpy as _np
    cors = []
    for recs in glyphs.values():
        if len(recs) < 2:
            continue
        ts = []
        for r in recs:
            a = _np.asarray(Image.fromarray((_np.clip(r["alpha"], 0, 1) * 255).astype(_np.uint8))
                            .resize((28, 28), Image.BILINEAR), _np.float32) / 255.0
            ts.append(((a - a.mean()) / (a.std() + 1e-6)).ravel())
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                cors.append(float((ts[i] @ ts[j]) / ts[i].size))
    return float(np.mean(cors)) if cors else None

MISASSIGN_BELOW = 0.40

def save_set(name, glyphs, meta):
    # Punctuation does not survive segmentation: a comma and a stray mark are the same shape
    # and the same size, so a failed punctuation row silently donates its specks to whatever
    # row is validated next. Letters and digits are kept; everything else falls back to the
    # font, where a full stop looks the same anyway.
    dropped = sorted(set(glyphs) - SAFE)
    glyphs = {c: v for c, v in glyphs.items() if c in SAFE}
    meta["dropped_unreliable"] = dropped
    corr = intra_letter_correlation(glyphs)
    meta["intra_letter_correlation"] = round(corr, 3) if corr is not None else None
    if corr is not None and corr < MISASSIGN_BELOW:
        raise SystemExit(
            f"REJECTED: intra-letter correlation {corr:.3f} < {MISASSIGN_BELOW}.\n"
            f"Forms filed under one character do not resemble each other, which means the "
            f"sheet was segmented wrong and letters are mislabelled. Open the sheet-*.png "
            f"files and look. Nothing was written.")
    d = os.path.join(SETS, name)
    os.makedirs(d, exist_ok=True)
    index = {}
    for ch, variants in glyphs.items():
        slug = f"u{ord(ch):04x}"
        recs = []
        for i, v in enumerate(variants):
            fn = f"{slug}_{i}.png"
            Image.fromarray((np.clip(v["alpha"], 0, 1) * 255).astype(np.uint8), "L") \
                .save(os.path.join(d, fn))
            recs.append({"file": fn, "base_dy": round(v["base_dy"], 4),
                         "w_xh": round(v["w_xh"], 4), "h_xh": round(v["h_xh"], 4)})
        index[ch] = recs
    meta["glyphs"] = index
    meta["coverage"] = len(index)
    meta["variants_total"] = sum(len(v) for v in index.values())
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=2)
    return d

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

def contact_sheet(name):
    d = os.path.join(SETS, name)
    meta = json.load(open(os.path.join(d, "meta.json")))
    order = sorted(meta["glyphs"], key=lambda c: (c.isdigit(), c.isupper(), c))
    cell, cols = 72, 16
    rowsn = (sum(len(meta["glyphs"][c]) for c in order) + cols - 1) // cols
    sheet = Image.new("L", (cols * cell, max(1, rowsn) * cell), 255)
    i = 0
    for ch in order:
        for rec in meta["glyphs"][ch]:
            g = Image.open(os.path.join(d, rec["file"]))
            g.thumbnail((cell - 10, cell - 10), Image.LANCZOS)
            inv = Image.eval(g, lambda v: 255 - v)
            sheet.paste(inv, ((i % cols) * cell + 5, (i // cols) * cell + 5))
            i += 1
    out = os.path.join(d, "contact.png")
    sheet.save(out)
    return out, meta

def main():
    ap = argparse.ArgumentParser(description="mint a handwriting glyph set from an image model")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mint")
    m.add_argument("--name", required=True)
    m.add_argument("--style", default="neat but natural everyday handwriting")
    m.add_argument("--ink", default="blue ballpoint pen")
    m.add_argument("--repeats", type=int, default=3, help="times the set is written per sheet")
    m.add_argument("--model", default=CHEAP)
    m.add_argument("--good", action="store_true", help=f"use {GOOD} instead")
    m.add_argument("--sheets", default="lower,upper,digits")
    m.add_argument("--retries", type=int, default=2)

    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("--name", required=True)
    a = ap.parse_args()

    if a.cmd == "list":
        if not os.path.isdir(SETS):
            print("no glyph sets yet"); return
        for n in sorted(os.listdir(SETS)):
            p = os.path.join(SETS, n, "meta.json")
            if os.path.exists(p):
                mm = json.load(open(p))
                print(f"  {n:<22} {mm['coverage']} chars, {mm['variants_total']} forms, "
                      f"${mm.get('cost_usd', 0):.3f}, {mm.get('model','?')}")
        return

    if a.cmd == "show":
        out, mm = contact_sheet(a.name)
        print(json.dumps({"contact_sheet": out, "coverage": mm["coverage"],
                          "variants_total": mm["variants_total"],
                          "chars": "".join(sorted(mm["glyphs"]))}, indent=2))
        return

    key = load_key()
    if not key:
        sys.exit("no OPENROUTER_API_KEY (env or ~/.env.master)")
    model = GOOD if a.good else a.model
    d = os.path.join(SETS, a.name)
    os.makedirs(d, exist_ok=True)
    glyphs, cost, notes = {}, 0.0, []
    for kind in [s.strip() for s in a.sheets.split(",") if s.strip()]:
        rows = SHEETS[kind]
        for attempt in range(a.retries + 1):
            img, c = call_model(prompt_for(rows, a.style, a.ink, a.repeats), key, model)
            cost += c
            img.save(os.path.join(d, f"sheet-{kind}-{attempt}.png"))
            got, ns = segment(img, rows, a.repeats)
            n_new = sum(len(v) for v in got.values())
            sys.stderr.write(f"  {kind} attempt {attempt+1}: {len(got)} chars, "
                             f"{n_new} forms, ${c:.4f}\n")
            for note in ns:
                sys.stderr.write(f"      {note}\n")
            for ch, vs in got.items():
                glyphs.setdefault(ch, []).extend(vs)
            notes += [f"{kind}: {x}" for x in ns]
            # a sheet that yielded most of its rows is good enough; stop paying
            if len(got) >= len("".join(rows)) * 0.8:
                break
    if not glyphs:
        sys.exit("no glyphs segmented — look at the sheet-*.png files in " + d)
    out = save_set(a.name, glyphs, {"model": model, "style": a.style, "ink": a.ink,
                                    "repeats": a.repeats, "cost_usd": round(cost, 4),
                                    "notes": notes})
    cs, mm = contact_sheet(a.name)
    print(json.dumps({"glyphset": out, "coverage": mm["coverage"],
                      "variants_total": mm["variants_total"], "cost_usd": round(cost, 4),
                      "intra_letter_correlation": mm.get("intra_letter_correlation"),
                      "contact_sheet": cs,
                      "chars": "".join(sorted(mm["glyphs"])),
                      "use": f"--glyphset {a.name}"}, indent=2))
    print("\nLOOK AT THE CONTACT SHEET before using this set:", cs, file=sys.stderr)

if __name__ == "__main__":
    main()
