#!/usr/bin/env python3
"""
serve — our version of handtextai.com, running on this machine.

Same shape as theirs (editor on the left, settings, Generate, page previews, PDF out) and
the same request decomposition, so the contract is familiar:

    POST /api/generate   {text, settings:{paper,font,effects,general}}  -> page PNGs
    POST /api/pdf        {generation_id}                               -> application/pdf
    POST /api/zip        {generation_id}                               -> every page as a PNG
    GET  /api/fonts                                                    -> installed faces

Two things theirs does not do:
  * every page comes back with its forensic realism score, so you can see what a setting
    actually bought instead of guessing
  * nothing leaves the machine

Standard library only — no framework, no build step:   python3 scripts/serve.py
"""
import base64, hashlib, http.server, io, json, os, socketserver, subprocess, sys, tempfile
import threading, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
STORE = os.path.join(tempfile.gettempdir(), "hyperwrite-serve")
os.makedirs(STORE, exist_ok=True)

sys.path.insert(0, HERE)
import hyperwrite as HW                                            # noqa: E402

# settings key -> hyperwrite flag. Mirrors handtextai's paper/font/effects/general split.
FLAGMAP = {
    ("paper", "style_id"): "--paper", ("paper", "format_id"): "--pagesize",
    ("font", "family"): "--font", ("font", "size"): "--size",
    ("font", "ink"): "--ink",
    ("effects", "variation"): "--wobble", ("effects", "variants"): "--variants",
    ("effects", "drift"): "--drift", ("effects", "pressure"): "--pressure",
    ("effects", "grain"): "--grain", ("effects", "bleed"): "--bleed",
    ("effects", "pool"): "--pool", ("effects", "skip"): "--skip",
    ("effects", "showthrough"): "--showthrough", ("effects", "capture"): "--capture",
    ("general", "messiness"): "--messiness", ("general", "slant"): "--slant",
    ("general", "sag"): "--sag", ("general", "linestart"): "--linestart",
    ("general", "word_space"): "--word-space", ("general", "dpi"): "--dpi",
    ("general", "seed"): "--seed", ("general", "max_pages"): "--max-pages",
    # 2026-09-24 parity with handtextai's Print/Photo switch, realism steps and page look
    ("output", "mode"): "--mode", ("output", "scene"): "--scene", ("output", "view"): "--view",
    ("effects", "realism"): "--realism", ("effects", "blur"): "--blur",
    ("effects", "shading"): "--shading", ("effects", "texture"): "--texture",
    ("effects", "ink_flow"): "--ink-flow", ("paper", "color"): "--paper-color",
    ("font", "letter_spacing"): "--letter-spacing", ("general", "align"): "--align",
    # 2026-09-28 from saurabhdaware/text-to-handwriting: page effects, a paper image, your font
    ("effects", "effect"): "--effect", ("effects", "shadow"): "--shadow",
    ("effects", "contrast"): "--contrast", ("paper", "margin_top"): "--margin-top",
    ("paper", "image"): "--paper-image",
}

# An upload arrives as {"name": "hand.otf", "data": <base64>} under settings.font.upload or
# settings.paper.upload. It is stored under its own hash, so a name from the browser never
# becomes a path, and it is opened once here, so a bad file is a 400 rather than a failed render.
UPLOADS = {("font", "family"): (".ttf", ".otf"), ("paper", "image"): (".png", ".jpg", ".jpeg")}
MAX_UPLOAD = 12 * 1024 * 1024
MAX_BODY = 2 * MAX_UPLOAD + (1 << 20)          # two base64 uploads and the text
MAX_PIXELS = 50_000_000                        # a 600-dpi A3 scan is 35 MP

def upload_dir():
    return os.path.join(STORE, "uploads")

def store_upload(group, key, up):
    if not isinstance(up, dict) or not isinstance(up.get("data"), str) or not up["data"]:
        raise ValueError(f"{group} upload needs a name and base64 data")
    allowed = UPLOADS[(group, key)]
    ext = os.path.splitext(str(up.get("name", "")).lower())[1]
    if ext not in allowed:
        raise ValueError(f"{group} upload must be one of {', '.join(allowed)}, got {ext or 'no extension'}")
    try:
        raw = base64.b64decode(up["data"], validate=True)
    except ValueError:
        raise ValueError(f"{group} upload is not valid base64")
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError(f"{group} upload is empty or over {MAX_UPLOAD >> 20} MB")
    d = upload_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, hashlib.sha256(raw).hexdigest()[:24] + ext)
    if not os.path.exists(path):
        open(path, "wb").write(raw)
    from PIL import Image, ImageFont
    try:
        if group == "font":
            ImageFont.truetype(path, 24).getbbox("Ag")
        else:
            with Image.open(path) as im:
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError(f"{im.width}x{im.height} is over {MAX_PIXELS // 10**6} MP")
                im.load()                       # verify() passes a truncated JPEG; load() does not
    except Exception as e:                      # Pillow raises several types for a bad file
        os.remove(path)
        raise ValueError(f"{group} upload could not be opened: {e}")
    return path

def resolve_uploads(settings):
    """A copy of settings with each upload stored and replaced by its path. A paper image
    only ever comes from an upload: a path typed into the request is refused."""
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    out = dict(settings)
    for group in ("paper", "font", "effects", "general", "output"):
        if out.get(group) is not None and not isinstance(out[group], dict):
            raise ValueError(f"settings.{group} must be an object")
        out[group] = dict(out.get(group) or {})
    if out["paper"].get("image"):
        raise ValueError("a paper image must be uploaded as paper.upload, not given as a path")
    for (group, key) in UPLOADS:
        up = out[group].pop("upload", None)
        if up is not None:
            out[group][key] = store_upload(group, key, up)
    return out

def build_cmd(text_path, out_path, settings):
    cmd = [sys.executable, os.path.join(HERE, "hyperwrite.py"),
           "--file", text_path, "--out", out_path]
    for (group, key), flag in FLAGMAP.items():
        v = (settings.get(group) or {}).get(key)
        if v in (None, ""):
            continue
        cmd += [flag, str(v)]
    if settings.get("landscape"):
        cmd.append("--landscape")
    return cmd

# The engine's own source is part of every cache key, so a render made by older code is never
# served after the code changes (the store lives in the temp folder and outlives the server).
ENGINE = hashlib.sha256(b"".join(
    open(os.path.join(HERE, f), "rb").read() for f in sorted(os.listdir(HERE))
    if f.endswith(".py"))).hexdigest()[:12]
RENDER_TIMEOUT = 900

def generate(text, settings):
    gid = hashlib.sha256(
        (ENGINE + text + json.dumps(settings, sort_keys=True)).encode()).hexdigest()[:16]
    d = os.path.join(STORE, gid)
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "report.json")):
        return gid, json.load(open(os.path.join(d, "report.json")))
    os.makedirs(d, exist_ok=True)
    tp = os.path.join(d, "source.txt")
    open(tp, "w").write(text)
    try:
        r = subprocess.run(build_cmd(tp, os.path.join(d, "page.png"), settings),
                           capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"render took over {RENDER_TIMEOUT} s and was stopped")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:] or "render failed")
    pages = sorted(f for f in os.listdir(d)
                   if f.startswith("page") and f.endswith(".png"))
    report = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    report["pages_files"] = pages
    json.dump(report, open(os.path.join(d, "report.json"), "w"))
    return gid, report

def score(gid, page):
    d = os.path.join(STORE, gid)
    r = subprocess.run([sys.executable, os.path.join(HERE, "judge.py"),
                        os.path.join(d, page), "--json"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)[0]
    except (ValueError, IndexError):
        return None

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            p = os.path.join(WEB, "index.html")
            return self._send(200, open(p, "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/fonts":
            have = [k for k, paths in HW.FONTS.items()
                    if any(os.path.exists(os.path.expanduser(x)) for x in paths)]
            fonts = list(HW.hw_fonts.CATALOG) + [k for k in have if k not in HW.hw_fonts.CATALOG]
            import hw_scene
            scenes = sorted(n for n, p in hw_scene.manifest()["plates"].items() if p.get("quad"))
            return self._send(200, json.dumps({"fonts": fonts,
                                               "papers": sorted(HW.PAPERS),
                                               "inks": sorted(HW.INKS),
                                               "formats": sorted(HW.PAGE_MM),
                                               "scenes": ["random"] + scenes,
                                               "realism": sorted(HW.REALISM),
                                               "effects": sorted(HW.hw_effects.EFFECTS)}))
        if u.path.startswith("/api/page/"):
            _, _, _, gid, name = u.path.split("/", 4)
            p = os.path.join(STORE, gid, os.path.basename(name))
            if not os.path.exists(p):
                return self._send(404, json.dumps({"error": "no such page"}))
            return self._send(200, open(p, "rb").read(), "image/png")
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            self.close_connection = True
            return self._send(413, json.dumps({"error": f"request over {MAX_BODY >> 20} MB"}))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, json.dumps({"error": "bad json"}))
        if not isinstance(body, dict):
            return self._send(400, json.dumps({"error": "the body must be a JSON object"}))
        u = urllib.parse.urlparse(self.path)

        if u.path == "/api/generate":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, json.dumps({"error": "no text"}))
            try:
                settings = resolve_uploads(body.get("settings") or {})
            except ValueError as e:
                return self._send(400, json.dumps({"error": str(e)}))
            try:
                gid, rep = generate(text, settings)
            except RuntimeError as e:
                return self._send(500, json.dumps({"error": str(e)}))
            out = {"generation_id": gid, "pages": rep.get("pages_files", []),
                   "seed": rep.get("seed"), "collision_rate": rep.get("collision_rate")}
            if body.get("score") and out["pages"]:
                out["forensic"] = score(gid, out["pages"][0])
            return self._send(200, json.dumps(out))

        if u.path in ("/api/pdf", "/api/zip"):
            gid = body.get("generation_id", "")
            d = os.path.join(STORE, os.path.basename(gid))
            pages = sorted(f for f in os.listdir(d)
                           if f.startswith("page") and f.endswith(".png")) \
                if os.path.isdir(d) else []
            if not pages:
                return self._send(404, json.dumps({"error": "nothing generated"}))
            if u.path == "/api/zip":
                # every page as its own PNG, like text-to-handwriting's per-page download
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for i, p in enumerate(pages):
                        z.write(os.path.join(d, p), f"page-{i + 1:02d}.png")
                return self._send(200, buf.getvalue(), "application/zip")
            from PIL import Image
            ims = [Image.open(os.path.join(d, p)).convert("RGB") for p in pages]
            buf = io.BytesIO()
            ims[0].save(buf, "PDF", save_all=True, append_images=ims[1:], resolution=200)
            return self._send(200, buf.getvalue(), "application/pdf")

        return self._send(404, json.dumps({"error": "not found"}))

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

def free_port(start):
    """Walk up until a port binds. 8787 was already held by an unrelated bun process on this
    machine, and 'Address already in use' at boot reads like the tool is broken."""
    import socket
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start

def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    port = free_port(want)
    if port != want:
        print(f"port {want} is taken, using {port}")
    with Server(("127.0.0.1", port), Handler) as srv:
        print(f"hyperwrite  ->  http://127.0.0.1:{port}", flush=True)
        print("nothing leaves this machine.  ctrl-c to stop", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")

if __name__ == "__main__":
    main()
