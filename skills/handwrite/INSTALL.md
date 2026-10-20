# Install handwrite

handwrite turns text or Markdown into pages that look written by hand (PDF, PNG, JPG or ZIP).
It is a skill for Claude Code and Codex, and a plain Python CLI.

## 1. Requirements

- Python 3.10 or newer
- `pip install pillow numpy reportlab pypdf`
- Internet on first run: fonts download from Google Fonts into a local cache the first time a hand needs them

## 2. Put it where your agent looks

```bash
# Claude Code
mkdir -p ~/.claude/skills && cp -R handwrite ~/.claude/skills/handwrite
# Codex (same files, optional)
mkdir -p ~/.codex/skills && ln -s ~/.claude/skills/handwrite ~/.codex/skills/handwrite
```

Then type `/handwrite` in Claude Code or Codex, or ask for "a handwritten PDF of these notes".

## 3. Check it works (about 30 seconds, no network after fonts are cached)

```bash
cd ~/.claude/skills/handwrite
bash scripts/test.sh            # expect: 17 passed, 0 failed
python3 scripts/hyperwrite.py --text "Hello from my own hand" --out hello.pdf --seed 42
```

## 4. Use your own handwriting

The bundled `casual-blue` hand works out of the box. To write in your own hand, follow
`references/cloning-your-hand.md` (scan a sample sheet, mint a glyph set or a `.ttf`, then pass
`--font` or `--glyphset`). The `henry` and `notes` presets in this copy use `casual-blue`; the
author's personal glyph sets are not included.

## 5. Use it for coursework notes

Write the notes in Markdown (headings, lists, `$maths$`, tables), then:

```bash
python3 scripts/hyperwrite.py --file notes.md --out notes.pdf --preset notes --seed 7
```

Keep the same `--seed` across runs so every page looks like the same person wrote it.
Use `::: correction` / `::: end` blocks with `--correct-ink red` for a second-pen correction pass.

MIT licensed (see LICENSE). Fonts and third-party code keep their own licences (THIRD_PARTY.md).
