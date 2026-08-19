# Troubleshooting

Matched to the exact error text you see. If your problem is not here, open an
issue with the command you ran and the full output.

---

## Installing Claude Code

**`claude: command not found` right after installing**

The installer added `claude` to your PATH, but your open terminal window loaded
its PATH before that happened. **Close the terminal completely and open a new
one.** This catches most people.

If a fresh window still fails, check where it landed:

```bash
ls -l ~/.local/bin/claude          # Mac / Linux / WSL
```

**`The token '&&' is not a valid statement separator`**

You are in PowerShell but ran the CMD command. Use the PowerShell one:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Your prompt shows `PS C:\>` in PowerShell and `C:\>` without the `PS` in CMD.

**Login says my plan is not supported**

Claude Code needs a Pro, Max, Team, or Enterprise plan. The free Claude.ai tier
does not include it.

---

## Canvas token and connection

**`CANVAS_TOKEN is not set` — but I definitely pasted it**

Three things to check, in order:

1. **Is the file named exactly `.env`?** Some editors silently save it as
   `.env.txt`. Check with `ls -a` (Mac/Linux) or `dir` (Windows).
2. **Is it in the repo root**, next to `README.md`? Not inside `scripts/`.
3. **Is there a stray quote or space?** `CANVAS_TOKEN = "abc"` will not parse the
   way you expect. Write it bare: `CANVAS_TOKEN=abc`

**`401 Unauthorized from Canvas`**

The token is expired, revoked, or was copied incompletely. Canvas tokens are
long; if you copied from a truncated display you got a partial one. Generate a
fresh token and replace the value in `.env`.

Note that this is about the **token**, not your Canvas password, and not whether
you are logged into Canvas in your browser.

**`403 Forbidden` for one endpoint but everything else works**

This is almost never a token problem. It means that specific course hides that
tab from students — Files is the usual one. The harvest records it as a warning
in `courses/<CODE>/_canvas/INDEX.md` and carries on. Nothing is broken.

**`404 Not Found` during harvest**

Same idea: the course has that tab disabled. Pages is the common one. Recorded as
a warning, not a failure.

**`Network error reaching …`**

Check `CANVAS_BASE_URL`. It should be the address in your browser bar when you
are in Canvas, for example `https://myschool.instructure.com` — not a course URL,
and not a login or SSO address.

---

## Results that look wrong

**A course is missing from the dashboard**

Two causes, and the dashboard distinguishes them under `NOT COVERED ABOVE`:

- **No Canvas shell.** The instructor has not published the course. Nothing can
  see it, including you. Add a placeholder by hand in `data/courses.json` so it
  is not forgotten.
- **No assignments published yet.** The shell exists but is empty.

Neither means "nothing is due." That distinction is the point of that section.

**A course from last term keeps showing up**

`discover.py` keeps the term that most of your active enrollments belong to.
If it guessed wrong, run `python3 scripts/discover.py --all-terms` to see
everything, then delete the rows you do not want from `data/courses.json`.

**Deadlines are off by an hour or several**

The tool converts from UTC to the zone Canvas reports for your account. If it
could not read that, it prints a warning and falls back to UTC. Set it explicitly
in `.env`:

```
CANVAS_TIMEZONE=America/Chicago
```

Use an IANA zone name, not an abbreviation like `CST`.

**A due date changed and I did not notice**

That is exactly what `refresh.py` exists for. Run it *before* the dashboard,
every time. It diffs against the last run and prints moved due dates first. It
reports `no changes` in seconds when nothing moved, so there is no reason to skip
it.

**The dashboard shows no grades**

Most courses show nothing until the first graded item is returned. An empty grade
column early in a term is normal.

---

## Everything else

**Can I re-run setup?**

Yes. Every step is idempotent. `scaffold.py` never overwrites a file that already
exists, and `harvest.py` only overwrites its own `_canvas/` output — anything you
or an agent wrote elsewhere in a course folder is left alone.

**Will my token end up on GitHub?**

`.env` is gitignored, along with `data/` and `courses/`. Your token, your course
list, and your harvested coursework all stay local. Verify any time with:

```bash
git status --porcelain
```

**Does this submit anything for me?**

No. Nothing in this repo submits work. Assignments marked `browser` require your
own logged-in session anyway — Gradescope, publisher tools, and quiz engines all
live outside the Canvas API. Submission is your action.

**Python version**

Requires Python 3.11 or later (it uses `zoneinfo` and modern typing syntax).
Check with `python3 --version`. On Windows you may need `py -3` instead of
`python3`.
