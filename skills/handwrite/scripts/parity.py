#!/usr/bin/env python3
"""
parity — the side-by-side against handtextai.com, as one contact sheet.

Five inputs (a letter, class notes, a maths page, a table, a Russian paragraph) live in
evals/parity/inputs/. handtextai's output for the SAME text, captured from their editor's free
preview on 2026-09-24 (A4, College Ruled, default font, realism Off — the free tier), is in
evals/parity/theirs/. This renders ours for each input in Print mode and in Photo mode and lays
the three out in rows.

    python3 scripts/parity.py --out evals/parity/contact-sheet.jpg
    python3 scripts/parity.py --out sheet.png --judge      # plus a vision-model A/B, ~$0.01

The judge is a second opinion, not the gate. judge.py records why: a vision model reads collided
mush as fluent text because it guesses words from context. It is asked to COMPARE two pages of
the same text, which it does better than it scores one.
"""
import argparse, base64, io, json, os, subprocess, sys, urllib.request

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAR = os.path.join(ROOT, "evals", "parity")
INPUTS = ["1-letter", "2-notes", "3-math", "4-table", "5-russian"]
SCENES = {"1-letter": "oak-mug", "2-notes": "study-desk", "3-math": "concrete",
          "4-table": "clipboard", "5-russian": "window-shadow"}
JUDGE = "google/gemini-3-flash-preview"


def render(name, outdir, mode, seed):
    out = os.path.join(outdir, f"{name}-{mode}.png")
    cmd = [sys.executable, os.path.join(HERE, "hyperwrite.py"),
           "--file", os.path.join(PAR, "inputs", f"{name}.md"), "--out", out,
           "--paper", "college", "--pagesize", "a4", "--seed", str(seed), "--dpi", "170",
           "--max-pages", "1"]
    if mode == "photo":
        cmd += ["--mode", "photo", "--scene", SCENES[name], "--view", "closer"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{name} {mode} failed:\n{r.stderr[-800:]}")
    return out


def label_font(px):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(p):
            return ImageFont.truetype(p, px)
    return ImageFont.load_default()


def sheet(rows, out, cell_h=1100):
    heads = ["handtextai.com (free preview)", "hyperwrite, Print mode", "hyperwrite, Photo mode"]
    cells = []
    for row in rows:
        ims = []
        for p in row:
            im = Image.open(p).convert("RGB")
            k = cell_h / im.height
            ims.append(im.resize((int(im.width * k), cell_h), Image.LANCZOS))
        cells.append(ims)
    cw = max(im.width for r in cells for im in r)
    gap, top = 24, 70
    W = 3 * cw + 4 * gap
    H = top + len(cells) * (cell_h + gap) + gap
    S = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(S)
    f = label_font(34)
    for c, h in enumerate(heads):
        d.text((gap + c * (cw + gap) + 8, 18), h, fill=(30, 30, 30), font=f)
    for r, ims in enumerate(cells):
        y = top + r * (cell_h + gap)
        for c, im in enumerate(ims):
            x = gap + c * (cw + gap) + (cw - im.width) // 2
            S.paste(im, (x, y))
    S.save(out, quality=88) if out.lower().endswith((".jpg", ".jpeg")) else S.save(out)
    return out


def ask(key, a, b, what):
    def enc(p):
        im = Image.open(p).convert("RGB")
        im.thumbnail((1100, 1100))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode()
    prompt = (f"Two images of the same handwritten {what}. Image A first, image B second. "
              "Rate each 1-10 for LEGIBILITY (could a teacher read every word without guessing) "
              "and NATURAL (does it look like a person wrote it with a pen, not a font). Reply "
              'only with JSON: {"A":{"legible":n,"natural":n},"B":{"legible":n,"natural":n},'
              '"note":"one short sentence"}')
    body = json.dumps({"model": JUDGE, "max_tokens": 300, "reasoning": {"enabled": False},
                       "messages": [{"role": "user", "content": [
                           {"type": "text", "text": prompt},
                           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + enc(a)}},
                           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + enc(b)}}]}],
                       "usage": {"include": True}}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                  "X-Title": "hyperwrite-parity"})
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.load(r)
    txt = j["choices"][0]["message"]["content"].strip().strip("`").removeprefix("json").strip()
    return json.loads(txt), float(j.get("usage", {}).get("cost") or 0)


def main():
    ap = argparse.ArgumentParser(description="contact sheet vs handtextai")
    ap.add_argument("--out", default=os.path.join(PAR, "contact-sheet.jpg"))
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--judge", action="store_true", help="vision-model A/B per input")
    a = ap.parse_args()
    outdir = os.path.join(PAR, "out")
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for n in INPUTS:
        theirs = os.path.join(PAR, "theirs", f"{n}.jpg")
        rows.append([theirs, render(n, outdir, "print", a.seed), render(n, outdir, "photo", a.seed)])
        print(f"  {n}", file=sys.stderr)
    print(sheet(rows, os.path.expanduser(a.out)))
    if a.judge:
        sys.path.insert(0, HERE)
        from hw_scene import load_key
        key = load_key()
        what = {"1-letter": "letter", "2-notes": "class notes", "3-math": "maths page",
                "4-table": "table", "5-russian": "Russian letter"}
        spent, res = 0.0, {}
        for n, (theirs, ours, _) in zip(INPUTS, rows):
            for attempt in range(3):          # the judge sometimes returns broken JSON
                try:
                    v, c = ask(key, theirs, ours, what[n])
                    break
                except (ValueError, KeyError) as e:
                    v, c = {"A": None, "B": None, "note": f"unparsed: {e}"}, 0.0
            spent += c
            res[n] = {"handtextai": v["A"], "hyperwrite": v["B"], "note": v.get("note")}
        res["_cost_usd"] = round(spent, 5)
        side = os.path.splitext(os.path.expanduser(a.out))[0] + ".judge.json"
        json.dump(res, open(side, "w"), indent=2)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
