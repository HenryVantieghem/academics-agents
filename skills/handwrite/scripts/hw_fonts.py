#!/usr/bin/env python3
"""
hw_fonts — the font catalog, per-script fallback, and a bank that stacks several hands.

handtextai ships 95 numbered faces and filters them by script (Latin, Cyrillic, Arabic, Greek,
Devanagari, Hangul, Kana, CJK). Most are open-licence Google Fonts. This module names ~45 of
those open-licence handwriting faces, fetches them on first use into `assets/fonts/` (not in
git: several CJK hands are 4-12 MB), and falls back per character when the chosen hand has no
glyph for it. So a Cyrillic word in a Latin hand comes out in a Cyrillic hand instead of tofu.

    python3 scripts/hw_fonts.py list                 # every face, its scripts, cached or not
    python3 scripts/hw_fonts.py fetch --all          # warm the cache (about 90 MB)
    python3 scripts/hw_fonts.py fetch kalam neucha   # just these
    python3 scripts/hw_fonts.py covers caveat "Привет αβγ ∫"

Coverage comes from the font's own cmap table, parsed here, because Pillow cannot say whether
a font has a glyph and a missing glyph renders as a plausible-looking box.
"""
import os, struct, sys, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "assets", "fonts")
GF = "https://raw.githubusercontent.com/google/fonts/main/"

# name: (google/fonts path, file, scripts, what it looks like)
# L latin, C cyrillic, G greek, A arabic, H hebrew, D devanagari, T thai, K hangul,
# J japanese kana+kanji, Z chinese hanzi, M maths symbols
CATALOG = {
    "caveat":      ("ofl/caveat", "Caveat[wght].ttf", "LC", "quick everyday print, the default"),
    "kalam":       ("ofl/kalam", "Kalam-Regular.ttf", "LD", "round student print; Devanagari too"),
    "patrick":     ("ofl/patrickhand", "PatrickHand-Regular.ttf", "L", "neat upright print"),
    "indie":       ("ofl/indieflower", "IndieFlower-Regular.ttf", "L", "bubbly, loose"),
    "shadows":     ("ofl/shadowsintolight", "ShadowsIntoLight.ttf", "L", "thin, fast, narrow"),
    "gloria":      ("ofl/gloriahallelujah", "GloriaHallelujah.ttf", "L", "comic-book print"),
    "architect":   ("ofl/architectsdaughter", "ArchitectsDaughter-Regular.ttf", "L",
                    "drafting-table capitals"),
    "homemade":    ("apache/homemadeapple", "HomemadeApple-Regular.ttf", "L", "fast joined cursive"),
    "reenie":      ("ofl/reeniebeanie", "ReenieBeanie.ttf", "L", "scrawled, rushed"),
    "nothing":     ("ofl/nothingyoucoulddo", "NothingYouCouldDo.ttf", "L", "light joined scrawl"),
    "justanother": ("apache/justanotherhand", "JustAnotherHand-Regular.ttf", "L", "tall narrow marker"),
    "dawning":     ("ofl/dawningofanewday", "DawningofaNewDay.ttf", "L", "slanted, airy cursive"),
    "aurore":      ("ofl/labelleaurore", "LaBelleAurore.ttf", "L", "old-fashioned cursive"),
    "cedarville":  ("ofl/cedarvillecursive", "Cedarville-Cursive.ttf", "L", "school cursive"),
    "dancing":     ("ofl/dancingscript", "DancingScript[wght].ttf", "L", "bouncy joined script"),
    "schoolbell":  ("apache/schoolbell", "Schoolbell-Regular.ttf", "L", "primary-school print"),
    "comingsoon":  ("apache/comingsoon", "ComingSoon-Regular.ttf", "L", "casual felt tip"),
    "sueellen":    ("ofl/sueellenfrancisco", "SueEllenFrancisco-Regular.ttf", "L", "very tall, thin"),
    "sunrise":     ("ofl/waitingforthesunrise", "WaitingfortheSunrise.ttf", "L", "loose teenage print"),
    "rocksalt":    ("apache/rocksalt", "RockSalt-Regular.ttf", "L", "heavy marker scrawl"),
    "zeyada":      ("ofl/zeyada", "Zeyada.ttf", "L", "hurried joined hand"),
    "gochi":       ("ofl/gochihand", "GochiHand-Regular.ttf", "L", "chunky marker"),
    "handlee":     ("ofl/handlee", "Handlee-Regular.ttf", "L", "tidy rounded print"),
    "kristi":      ("ofl/kristi", "Kristi-Regular.ttf", "L", "elegant pointed cursive"),
    "annie":       ("ofl/annieuseyourtelescope", "AnnieUseYourTelescope-Regular.ttf", "L",
                    "spiky, energetic"),
    "delius":      ("ofl/delius", "Delius-Regular.ttf", "L", "rounded, legible"),
    "caveatbrush": ("ofl/caveatbrush", "CaveatBrush-Regular.ttf", "L", "Caveat in brush pen"),
    "neucha":      ("ofl/neucha", "Neucha.ttf", "LC", "Russian school print"),
    "marck":       ("ofl/marckscript", "MarckScript-Regular.ttf", "LC", "Russian joined cursive"),
    "pangolin":    ("ofl/pangolin", "Pangolin-Regular.ttf", "LC", "round felt tip"),
    "playpen":     ("ofl/playpensans", "PlaypenSans[wght].ttf", "LCGM", "clean teacher print"),
    "playpen-ar":  ("ofl/playpensansarabic", "PlaypenSansArabic[wght].ttf", "LA",
                    "Arabic, teacher print"),
    "playpen-he":  ("ofl/playpensanshebrew", "PlaypenSansHebrew[wght].ttf", "LH",
                    "Hebrew, teacher print"),
    "playpen-dev": ("ofl/playpensansdeva", "PlaypenSansDeva[wght].ttf", "LD",
                    "Devanagari, teacher print"),
    "playpen-th":  ("ofl/playpensansthai", "PlaypenSansThai[wght].ttf", "LT", "Thai, teacher print"),
    "ruqaa":       ("ofl/arefruqaa", "ArefRuqaa-Regular.ttf", "LA", "Arabic Ruqaa, the everyday hand"),
    "mali":        ("ofl/mali", "Mali-Regular.ttf", "LT", "Thai and Latin, rounded"),
    "sriracha":    ("ofl/sriracha", "Sriracha-Regular.ttf", "LT", "Thai and Latin marker"),
    "nanumpen":    ("ofl/nanumpenscript", "NanumPenScript-Regular.ttf", "LK", "Korean pen"),
    "gaegu":       ("ofl/gaegu", "Gaegu-Regular.ttf", "LK", "Korean, soft pencil"),
    "klee":        ("ofl/kleeone", "KleeOne-Regular.ttf", "LCGJM",
                    "Japanese textbook pen; Greek and maths symbols"),
    "yomogi":      ("ofl/yomogi", "Yomogi-Regular.ttf", "LJ", "Japanese casual pen"),
    "kurenaido":   ("ofl/zenkurenaido", "ZenKurenaido-Regular.ttf", "LJ", "Japanese brush pen"),
    "mashanzheng": ("ofl/mashanzheng", "MaShanZheng-Regular.ttf", "LZ", "Chinese regular script"),
    "longcang":    ("ofl/longcang", "LongCang-Regular.ttf", "LZ", "Chinese running hand"),
    "zhimang":     ("ofl/zhimangxing", "ZhiMangXing-Regular.ttf", "LZ", "Chinese fast cursive"),
    # one of text-to-handwriting's three hands (2026-09-28); the other two are homemade, caveat
    "liujian":     ("ofl/liujianmaocao", "LiuJianMaoCao-Regular.ttf", "LZ",
                    "Chinese grass script; small, quick Latin"),
}

# Faces already on a Mac. Kept so the engine works offline with nothing fetched.
SYSTEM = {
    "caveat":     ["~/Library/Fonts/Caveat-Regular.ttf", "~/Library/Fonts/Caveat-Medium.ttf"],
    "bradley":    ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"],
    "noteworthy": ["/System/Library/Fonts/Noteworthy.ttc"],
    "marker":     ["/System/Library/Fonts/MarkerFelt.ttc"],
    "chalk":      ["/System/Library/Fonts/Supplemental/Chalkduster.ttf"],
    "snell":      ["/System/Library/Fonts/Supplemental/SnellRoundhand.ttc"],
    "savoye":     ["/System/Library/Fonts/Supplemental/Savoye LET.ttc"],
    "brush":      ["/System/Library/Fonts/Supplemental/Brush Script.ttf"],
    "chancery":   ["/System/Library/Fonts/Supplemental/Apple Chancery.ttf"],
    "unicode":    ["/Library/Fonts/Arial Unicode.ttf"],
}

# Which hands to try, in order, for a character the chosen hand lacks.
FALLBACK = {
    "L": ["caveat", "patrick"], "C": ["neucha", "caveat", "marck", "playpen"],
    "G": ["playpen", "klee"], "A": ["ruqaa", "playpen-ar"], "H": ["playpen-he"],
    "D": ["kalam", "playpen-dev"], "T": ["mali", "playpen-th"], "K": ["nanumpen", "gaegu"],
    "J": ["klee", "yomogi"], "Z": ["mashanzheng", "longcang", "klee"],
    "M": ["klee", "playpen", "unicode"], "?": ["klee", "playpen", "unicode"],
}
COMPLEX = set("ADHT")        # scripts that must be shaped as whole words, never per letter
RTL = set("AH")


def script_of(ch):
    """One-letter script code for a character, matching CATALOG's codes."""
    o = ord(ch)
    if o < 0x250 or 0x1E00 <= o < 0x1F00:
        return "L"
    if 0x370 <= o < 0x400 or 0x1F00 <= o < 0x2000:
        return "G"
    if 0x400 <= o < 0x530:
        return "C"
    if 0x590 <= o < 0x600 or 0xFB1D <= o < 0xFB50:
        return "H"
    if 0x600 <= o < 0x800 or 0xFB50 <= o < 0xFE00 or 0xFE70 <= o < 0xFF00:
        return "A"
    if 0x900 <= o < 0x980:
        return "D"
    if 0xE00 <= o < 0xE80:
        return "T"
    if 0xAC00 <= o < 0xD7B0 or 0x1100 <= o < 0x1200 or 0x3130 <= o < 0x3190:
        return "K"
    if 0x3040 <= o < 0x3100 or 0x31F0 <= o < 0x3200:
        return "J"
    if 0x4E00 <= o < 0xA000 or 0x3400 <= o < 0x4DC0 or 0x3000 <= o < 0x3040 or 0xFF00 <= o < 0xFFF0:
        return "Z"
    if unicodedata.category(ch) in ("Sm", "So") or 0x2000 <= o < 0x2C00:
        return "M"
    return "?"


def is_rtl(text):
    return any(script_of(c) in RTL for c in text)


def needs_shaping(text):
    return any(script_of(c) in COMPLEX for c in text)


# ------------------------------------------------------------------ cmap
def _cmap_from(buf, base):
    """Codepoints covered by the font whose table directory starts at `base`."""
    num = struct.unpack(">H", buf[base + 4:base + 6])[0]
    tables = {}
    for i in range(num):
        rec = base + 12 + 16 * i
        tag = buf[rec:rec + 4].decode("latin-1")
        tables[tag] = struct.unpack(">II", buf[rec + 8:rec + 16])
    if "cmap" not in tables:
        return set()
    off = tables["cmap"][0]
    n = struct.unpack(">H", buf[off + 2:off + 4])[0]
    best = None
    for i in range(n):
        pid, eid, sub = struct.unpack(">HHI", buf[off + 4 + 8 * i:off + 12 + 8 * i])
        fmt = struct.unpack(">H", buf[off + sub:off + sub + 2])[0]
        rank = {12: 2, 4: 1}.get(fmt, 0)
        if pid in (0, 3) and rank and (best is None or rank > best[0]):
            best = (rank, off + sub, fmt)
    if best is None:
        return set()
    _, p, fmt = best
    out = set()
    if fmt == 12:
        groups = struct.unpack(">I", buf[p + 12:p + 16])[0]
        for g in range(groups):
            a, b, _ = struct.unpack(">III", buf[p + 16 + 12 * g:p + 28 + 12 * g])
            out.update(range(a, b + 1))
    else:
        segx2 = struct.unpack(">H", buf[p + 6:p + 8])[0]
        seg = segx2 // 2
        ends = struct.unpack(f">{seg}H", buf[p + 14:p + 14 + segx2])
        starts = struct.unpack(f">{seg}H", buf[p + 16 + segx2:p + 16 + 2 * segx2])
        for a, b in zip(starts, ends):
            if a != 0xFFFF:
                out.update(range(a, b + 1))
    return out


_COVER = {}


def coverage(path, index=0):
    """Set of codepoints the font maps. Parsed from the file, cached per path."""
    key = (path, index)
    if key not in _COVER:
        try:
            buf = open(path, "rb").read()
            base = 0
            if buf[:4] == b"ttcf":
                base = struct.unpack(">I", buf[12 + 4 * index:16 + 4 * index])[0]
            _COVER[key] = _cmap_from(buf, base)
        except (OSError, struct.error):
            _COVER[key] = set()
    return _COVER[key]


# ------------------------------------------------------------------ fetch + resolve
def cached_path(name):
    ent = CATALOG.get(name)
    return os.path.join(CACHE, ent[1]) if ent else None


def fetch(name, quiet=False):
    """Download one catalog face (and its licence) into the cache. Returns its path."""
    d, f, _, _ = CATALOG[name]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return out
    if not quiet:
        sys.stderr.write(f"  fetching font {name} ({f}) from google/fonts\n")
    url = GF + d + "/" + urllib.request.quote(f)
    tmp = out + ".part"
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as w:
        w.write(r.read())
    os.replace(tmp, out)
    lic = "LICENSE.txt" if d.startswith("apache/") else "OFL.txt"
    lp = os.path.join(CACHE, f"{name}.{lic}")
    if not os.path.exists(lp):
        try:
            with urllib.request.urlopen(GF + d + "/" + lic, timeout=60) as r:
                open(lp, "wb").write(r.read())
        except OSError:
            pass
    return out


def resolve(name, allow_fetch=True):
    """Path for a font name, a catalog face, a system face, or a path to any .ttf/.otf."""
    for p in SYSTEM.get(name, []):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    p = cached_path(name)
    if p and os.path.exists(p):
        return p
    if name in CATALOG and allow_fetch:
        try:
            return fetch(name)
        except OSError as e:
            sys.stderr.write(f"  could not fetch {name}: {e}\n")
            return None
    p = os.path.expanduser(name)
    return p if os.path.exists(p) else None


def fallback_chain(primary, text):
    """Font names worth loading for this text, primary first, only for scripts it uses."""
    need = {script_of(c) for c in text if not c.isspace()}
    if "$" in text or "\\" in text:
        need.add("M")                            # LaTeX names its symbols; the text has none
    names = [primary]
    for s in "LCGAHDTKJZM?":
        if s in need:
            names += [n for n in FALLBACK[s] if n not in names]
    return names


# ------------------------------------------------------------------ stacked bank
class FontStack:
    """A glyph bank that routes each character to the first hand that has it.

    Same interface as hyperwrite.GlyphBank (px, variants, tighten, advance, get, metrics), so the
    page renderer never knows it is holding more than one font. A shaped unit (an Arabic word, a
    Devanagari cluster) is routed by its first non-space character.
    """
    def __init__(self, banks, px=None):
        self.banks = banks                       # [(bank, codepoint set)]
        self.primary = banks[0][0]
        # the stack's em is the WRITING em; each face inside it is sized to match its x-height
        self.px = px or self.primary.px
        self.variants = max(b.variants for b, _ in banks)
        self._route = {}

    @property
    def letter_space(self):
        return getattr(self.primary, "letter_space", 0.0)

    @letter_space.setter
    def letter_space(self, v):
        for b, _ in self.banks:
            b.letter_space = v

    @property
    def tighten(self):
        return self.primary.tighten

    @tighten.setter
    def tighten(self, v):
        for b, _ in self.banks:
            b.tighten = v

    def bank_for(self, unit):
        key = next((c for c in unit if not c.isspace()), " ")
        if key not in self._route:
            pick = self.primary
            for b, cov in self.banks:
                if ord(key) in cov:
                    pick = b
                    break
            self._route[key] = pick
        return self._route[key]

    space = None          # set by the engine: a word gap is a property of the hand, not the font
    stroke_px = None      # the primary face's measured pen width

    def advance(self, unit):
        if unit == " ":
            return self.space if self.space else self.primary.advance(" ")
        return self.bank_for(unit).advance(unit)

    def get(self, unit, variant):
        return self.bank_for(unit).get(unit, variant)

    def metrics(self, unit):
        return self.bank_for(unit).metrics(unit)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="handwriting font catalog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("fetch")
    f.add_argument("names", nargs="*")
    f.add_argument("--all", action="store_true")
    c = sub.add_parser("covers")
    c.add_argument("name")
    c.add_argument("text")
    a = ap.parse_args()
    if a.cmd == "list":
        for n, (_, fn, sc, desc) in CATALOG.items():
            p = cached_path(n)
            state = "cached" if os.path.exists(p) else "fetch on use"
            print(f"{n:12} {sc:6} {state:13} {desc}")
        for n in SYSTEM:
            if resolve(n, allow_fetch=False):
                print(f"{n:12} {'L':6} {'system':13} macOS face")
    elif a.cmd == "fetch":
        names = list(CATALOG) if a.all else a.names
        for n in names:
            print(fetch(n))
    else:
        p = resolve(a.name)
        cov = coverage(p) if p else set()
        miss = sorted({ch for ch in a.text if not ch.isspace() and ord(ch) not in cov})
        print(f"{a.name}: {len(cov)} codepoints; missing {''.join(miss) or 'nothing'}")


if __name__ == "__main__":
    main()
