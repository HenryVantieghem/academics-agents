#!/usr/bin/env python3
"""
hw_math — lay out a LaTeX subset as handwriting.

handtextai renders maths with KaTeX in a handwriting face. A person writing maths does not
typeset it: they write the numerator, draw a bar under it, write the denominator, and draw the
root sign, the integral and the sigma as pen strokes. So this module turns LaTeX into a box of
two kinds of operation, and the page renderer does the writing:

    ("g", unit, x, y, scale)       write this character at (x, baseline y), this big
    ("s", [(x, y), ...], weight)   draw a pen stroke through these points

Coordinates are pixels relative to the box origin on its baseline, y down, like the page.

Supported: \\frac \\dfrac \\tfrac, \\sqrt and \\sqrt[n], ^ and _, \\sum \\prod \\int \\iint \\oint
\\lim with limits, \\left( \\right), Greek, the common relations and operators, \\sin \\cos \\log
and friends, \\text \\mathrm \\mathbf, \\vec \\hat \\bar \\overline, \\, \\; \\quad spacing,
\\cdot \\dots \\infty \\partial \\nabla. Anything unknown is written out as its name, so a
typo shows up on the page instead of vanishing.
"""
import re

GREEK = dict(alpha="α", beta="β", gamma="γ", delta="δ", epsilon="ε", varepsilon="ε", zeta="ζ",
             eta="η", theta="θ", vartheta="θ", iota="ι", kappa="κ", lambda_="λ", mu="μ", nu="ν",
             xi="ξ", pi="π", rho="ρ", sigma="σ", tau="τ", upsilon="υ", phi="φ", varphi="φ",
             chi="χ", psi="ψ", omega="ω", Gamma="Γ", Delta="Δ", Theta="Θ", Lambda="Λ", Xi="Ξ",
             Pi="Π", Sigma="Σ", Phi="Φ", Psi="Ψ", Omega="Ω")
GREEK["lambda"] = "λ"
SYMBOLS = dict(pm="±", mp="∓", times="×", div="÷", cdot="·", leq="≤", le="≤", geq="≥", ge="≥",
               neq="≠", ne="≠", approx="≈", equiv="≡", sim="~", to="→", rightarrow="→",
               leftarrow="←", Rightarrow="⇒", Leftarrow="⇐", iff="⇔", Leftrightarrow="⇔",
               infty="∞", partial="∂", nabla="∇", in_="∈", notin="∉", subset="⊂", cup="∪",
               cap="∩", forall="∀", exists="∃", degree="°", circ="°", prime="′", ldots="…",
               dots="…", cdots="⋯", langle="⟨", rangle="⟩", perp="⊥", angle="∠", therefore="∴",
               emptyset="∅", neg="¬", land="∧", lor="∨", ell="ℓ", hbar="ħ", propto="∝",
               lvert="|", rvert="|", mid="|", vert="|", star="*", ast="*")
SYMBOLS["in"] = "∈"
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "max", "min", "det",
         "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "lg", "gcd", "mod", "deg", "dim"}
BIGOPS = {"sum": "Σ", "prod": "Π", "int": "∫", "iint": "∫∫", "oint": "∮", "lim": "lim",
          "bigcup": "∪", "bigcap": "∩"}
SPACES = {",": 0.17, ":": 0.22, ";": 0.28, "!": -0.1, "quad": 1.0, "qquad": 2.0, " ": 0.28}
BINARY = set("+-=<>±∓×÷·≤≥≠≈≡→←⇒⇐⇔∈∉⊂∪∩∝~")


class Box:
    def __init__(self, w=0.0, asc=0.0, desc=0.0, ops=None):
        self.w, self.asc, self.desc, self.ops = w, asc, desc, ops or []

    def shifted(self, dx, dy):
        out = []
        for op in self.ops:
            if op[0] == "g":
                out.append(("g", op[1], op[2] + dx, op[3] + dy, op[4]))
            else:
                out.append(("s", [(x + dx, y + dy) for x, y in op[1]], op[2]))
        return out


def tokenize(src):
    return re.findall(r"\\[A-Za-z]+|\\.|[{}^_&\[\]]|\S|\s+", src)


class Layout:
    """measure(unit) -> (advance, ascent, descent) in px at scale 1."""

    def __init__(self, measure, em):
        self.measure, self.em = measure, em
        self.toks, self.i = [], 0

    # -------------------------------------------------------------- parsing
    def peek(self):
        while self.i < len(self.toks) and self.toks[self.i].isspace():
            self.i += 1
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def group_text(self):
        """Raw text of a {...} group, for \\text."""
        if self.peek() != "{":
            return self.take() or ""
        self.take()
        depth, out = 1, []
        while self.i < len(self.toks):
            t = self.toks[self.i]
            self.i += 1
            if t == "{":
                depth += 1
            elif t == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(t)
        return "".join(out)

    def arg(self, s):
        if self.peek() == "{":
            self.take()
            b = self.expr(s, stop="}")
            self.take()
            return b
        return self.atom(s) or Box()

    def expr(self, s, stop=None):
        parts = []
        while True:
            t = self.peek()
            if t is None or t == stop or (stop == "}" and t == "}") or t == "\\right":
                break
            a = self.atom(s)
            if a is None:
                continue
            a = self.scripts(a, s)
            parts.append(a)
        return self.hbox(parts)

    # -------------------------------------------------------------- building
    def glyph(self, unit, s, pad=0.0):
        adv, asc, desc = self.measure(unit)
        p = pad * self.em * s
        return Box(adv * s + 2 * p, asc * s, desc * s, [("g", unit, p, 0.0, s)])

    def word(self, text, s):
        parts = []
        for ch in text:
            if ch == " ":
                parts.append(Box(self.em * 0.28 * s))
            else:
                parts.append(self.glyph(ch, s))
        return self.hbox(parts)

    def hbox(self, parts):
        x, asc, desc, ops = 0.0, 0.0, 0.0, []
        for b in parts:
            ops += b.shifted(x, 0)
            x += b.w
            asc, desc = max(asc, b.asc), max(desc, b.desc)
        return Box(x, asc, desc, ops)

    def scripts(self, base, s):
        sup = sub = None
        while self.peek() in ("^", "_"):
            t = self.take()
            if t == "^":
                sup = self.arg(s * 0.68)
            else:
                sub = self.arg(s * 0.68)
        if getattr(base, "limits", False) and (sup or sub):
            return self.limits(base, sup, sub, s)
        if not sup and not sub:
            return base
        ops = list(base.ops)
        w = base.w
        asc, desc = base.asc, base.desc
        xs = base.w + self.em * 0.03 * s
        if sup:
            up = max(base.asc * 0.62, self.em * 0.30 * s) + sup.desc
            ops += sup.shifted(xs, -up)
            asc = max(asc, up + sup.asc)
            w = max(w, xs + sup.w)
        if sub:
            dn = max(base.desc * 0.8, self.em * 0.12 * s) + sub.asc * 0.55
            ops += sub.shifted(xs, dn)
            desc = max(desc, dn + sub.desc)
            w = max(w, xs + sub.w)
        return Box(w + self.em * 0.04 * s, asc, desc, ops)

    def limits(self, base, sup, sub, s):
        w = max(base.w, sup.w if sup else 0, sub.w if sub else 0)
        cx = lambda b: (w - b.w) / 2
        ops = base.shifted(cx(base), 0)
        asc, desc = base.asc, base.desc
        gap = self.em * 0.08 * s
        if sup:
            y = -(base.asc + gap + sup.desc)
            ops += sup.shifted(cx(sup), y)
            asc = -y + sup.asc
        if sub:
            y = base.desc + gap + sub.asc
            ops += sub.shifted(cx(sub), y)
            desc = y + sub.desc
        return Box(w + self.em * 0.1 * s, asc, desc, ops)

    def frac(self, s, small=False):
        k = 0.78 if small else 1.0
        num = self.arg(s * k)
        den = self.arg(s * k)
        axis = self.em * 0.25 * s
        gap = self.em * 0.10 * s
        pad = self.em * 0.10 * s
        w = max(num.w, den.w) + 2 * pad
        ops = num.shifted((w - num.w) / 2, -axis - gap - num.desc)
        ops += den.shifted((w - den.w) / 2, -axis + gap + den.asc)
        # a hand-drawn bar overshoots a little on both sides and is never dead level
        ops.append(("s", [(0.0, -axis), (w * 0.5, -axis + self.em * 0.012 * s), (w, -axis)], 1.0))
        asc = axis + gap + num.desc + num.asc
        desc = -axis + gap + den.asc + den.desc
        return Box(w + self.em * 0.08 * s, asc, max(desc, 0.0), ops)

    def sqrt(self, s):
        index = None
        if self.peek() == "[":
            self.take()
            index = self.expr(s * 0.6, stop="]")
            self.take()
        body = self.arg(s)
        e = self.em * s
        top = body.asc + e * 0.12
        bot = body.desc
        h = top + bot
        lead = e * 0.18 + h * 0.18
        x0 = index.w * 0.6 if index else 0.0
        pts = [(x0, -h * 0.35 + bot), (x0 + lead * 0.35, -h * 0.45 + bot),
               (x0 + lead * 0.7, bot), (x0 + lead, -top), (x0 + lead + body.w + e * 0.12, -top)]
        ops = [("s", pts, 1.0)] + body.shifted(x0 + lead + e * 0.06, 0)
        if index:
            ops += index.shifted(0, -h * 0.45 + bot - index.desc - e * 0.05)
        return Box(x0 + lead + body.w + e * 0.2, top + e * 0.06, bot, ops)

    def bigop(self, name, s):
        e = self.em * s
        if name in ("lim", "bigcup", "bigcap"):
            b = self.word(BIGOPS[name], s) if name == "lim" else self.glyph(BIGOPS[name], s * 1.4)
            b.limits = True
            return b
        if name in ("int", "iint", "oint"):
            h = e * 1.05
            ops, x = [], e * 0.12
            for _ in range(2 if name == "iint" else 1):
                # a long S: hook at the top, a slanted stem, a hook at the bottom
                ops.append(("s", [(x + e * 0.34, -h * 0.78), (x + e * 0.26, -h * 0.86),
                                  (x + e * 0.18, -h * 0.70), (x + e * 0.12, h * 0.05),
                                  (x + e * 0.06, h * 0.30), (x - e * 0.02, h * 0.34),
                                  (x - e * 0.06, h * 0.26)], 1.0))
                x += e * 0.28
            if name == "oint":
                ops.append(("s", [(x - e * 0.28 + e * 0.12 * c, -h * 0.25 + e * 0.12 * t)
                                  for c, t in ((1, 0), (0.3, 0.9), (-0.7, 0.3), (-0.2, -0.6),
                                               (0.9, -0.3), (1, 0.05))], 0.9))
            b = Box(x + e * 0.22, h * 0.86, h * 0.36, ops)
            b.limits = False
            return b
        w, h = e * 0.62, e * 0.78
        if name == "sum":
            pts = [(w, -h * 0.92), (0, -h * 0.95), (w * 0.52, -h * 0.40), (0.0, h * 0.18),
                   (w * 1.04, h * 0.16)]
            ops = [("s", pts, 1.0)]
        else:
            ops = [("s", [(0, -h * 0.92), (w, -h * 0.94)], 1.0),
                   ("s", [(w * 0.18, -h * 0.93), (w * 0.16, h * 0.16)], 1.0),
                   ("s", [(w * 0.82, -h * 0.93), (w * 0.84, h * 0.16)], 1.0)]
        b = Box(w + e * 0.12, h, h * 0.2, [(op[0], [(x + e * 0.05, y) for x, y in op[1]], op[2])
                                              for op in ops])
        b.limits = True
        return b

    def accent(self, kind, s):
        body = self.arg(s)
        e = self.em * s
        y = -body.asc - e * 0.08
        if kind == "vec":
            st = [("s", [(0, y), (body.w, y)], 0.8),
                  ("s", [(body.w - e * 0.12, y - e * 0.07), (body.w, y), (body.w - e * 0.12, y + e * 0.07)], 0.8)]
        elif kind == "hat":
            m = body.w / 2
            st = [("s", [(m - e * 0.12, y + e * 0.02), (m, y - e * 0.1), (m + e * 0.12, y + e * 0.02)], 0.8)]
        else:
            st = [("s", [(0, y), (body.w, y)], 0.8)]
        return Box(body.w, body.asc + e * 0.18, body.desc, body.ops + st)

    def delim(self, s):
        t = self.take() or "."
        t = {"\\{": "{", "\\}": "}", "\\langle": "⟨", "\\rangle": "⟩", "\\|": "‖",
             "\\lvert": "|", "\\rvert": "|"}.get(t, t)
        return t

    def fenced(self, s):
        left = self.delim(s)
        body = self.expr(s)
        right = "."
        if self.peek() == "\\right":
            self.take()
            right = self.delim(s)
        h = body.asc + body.desc
        _, a0, d0 = self.measure("(")
        k = max(1.0, h / max(1.0, (a0 + d0) * s) * 1.05)
        parts = []
        for d, where in ((left, "l"), (right, "r")):
            if d == ".":
                parts.append(None)
                continue
            g = self.glyph(d, s * k)
            # centre the stretched delimiter on the body, not on the baseline
            shift = (g.asc - g.desc) / 2 - (body.asc - body.desc) / 2
            parts.append(Box(g.w, g.asc - shift, g.desc + shift, g.shifted(0, shift)))
        seq = [p for p in (parts[0], body, parts[1]) if p is not None]
        return self.hbox(seq)

    def atom(self, s):
        t = self.take()
        if t is None:
            return None
        if t == "{":
            b = self.expr(s, stop="}")
            self.take()
            return b
        if t in ("}", "]", "&"):
            return None
        if t.startswith("\\"):
            name = t[1:]
            if name in SPACES:
                return Box(self.em * SPACES[name] * s)
            if name in ("frac", "dfrac", "cfrac"):
                return self.frac(s)
            if name == "tfrac":
                return self.frac(s, small=True)
            if name == "sqrt":
                return self.sqrt(s)
            if name in BIGOPS:
                return self.bigop(name, s)
            if name in ("left",):
                return self.fenced(s)
            if name in ("text", "mathrm", "textrm", "mathbf", "textbf", "operatorname", "mathit"):
                return self.word(self.group_text(), s)
            if name in ("vec", "hat", "bar", "overline", "widehat", "overrightarrow"):
                return self.accent({"overline": "bar", "widehat": "hat",
                                    "overrightarrow": "vec"}.get(name, name), s)
            if name in FUNCS:
                b = self.word(name, s)
                return Box(b.w + self.em * 0.12 * s, b.asc, b.desc, b.ops)
            if name in ("displaystyle", "limits", "nolimits", "big", "Big", "bigg", "Bigg"):
                return Box()
            ch = GREEK.get(name) or SYMBOLS.get(name)
            if ch:
                return self.op_glyph(ch, s)
            if len(name) == 1:
                return self.glyph(name, s)
            return self.word(name, s)
        if t.isspace():
            return None
        if t == "'" or t == "\\prime":
            e = self.em * s
            return Box(e * 0.2, e * 0.75, 0.0,
                       [("s", [(e * 0.16, -e * 0.72), (e * 0.07, -e * 0.48)], 0.9)])
        if t in ("-", "−"):
            # a handwriting face's hyphen is a short tick; a written minus is a proper dash
            e = self.em * s
            y = -e * 0.25
            return Box(e * 0.62, e * 0.3, 0.0, [("s", [(e * 0.12, y), (e * 0.50, y - e * 0.01)], 1.0)])
        return self.op_glyph(t, s)

    def op_glyph(self, ch, s):
        return self.glyph(ch, s, pad=0.14 if ch in BINARY else 0.0)

    def run(self, src, s=1.0):
        self.toks, self.i = tokenize(src), 0
        return self.expr(s)


def layout(src, measure, em, scale=1.0):
    """LaTeX source -> Box. `em` is the writing em in px; `measure` gives glyph metrics."""
    return Layout(measure, em).run(src, scale)
