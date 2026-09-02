# academics-agents

**An agent-operated command centre for your coursework, backed by the Canvas LMS API.**

Point it at your Canvas account and it builds a local, readable mirror of every
class you are enrolled in — assignments, quizzes, pages, modules, files — then
grows a per-course sub-skill so an AI agent actually knows your classes instead
of guessing about them.

Zero third-party dependencies. Python 3.11+ and a Canvas token, nothing else.

**Requirements:** Python 3.11 or later, git, and a Canvas account. Works on macOS,
Windows, and Linux. Not sure you have git and Python? See
[Before you start](#before-you-start). Stuck at any point? [docs/troubleshooting.md](docs/troubleshooting.md)
is matched to the exact error text.

---

## What you get

```
data/courses.json              your course registry
courses/<CODE>/
  00-context/COURSE-CONTEXT.md   grading, policies, submission routing, traps
  00-context/SKILL.md            the per-course sub-skill an agent loads
  _canvas/                       readable mirror of everything Canvas exposes
  01-syllabus/ … 06-notes/       where material accumulates
scripts/                       the engine
```

- **A dashboard that will not lie to you** — grades, overdue, upcoming, *and* an
  explicit list of what it cannot see, so a clean report never implies "nothing
  is due" when the truth is "nothing is visible."
- **Change detection.** `refresh.py` diffs against the last run and leads with
  the one thing that actually costs marks: **a due date that moved.**
- **Submission routing per assignment** — `api` (pushable), `browser` (needs your
  own logged-in session: Gradescope, publisher tools, quiz engines), or `none`
  (in class). This is not obvious from the API and it decides what help is even
  possible.

---

## Before you start

Two things have to exist before step 1, and both checks take ten seconds. If you
have ever cloned a repo on this machine, you almost certainly have both already.

### git

```bash
git --version
```

A version number means you are done. On a Mac with nothing installed yet, that
command makes macOS pop up a dialog offering the **command line developer tools**
— click Install and wait a few minutes. That package contains git and it is the
only thing you need; you do not need the full Xcode download. You can also start
it yourself:

```bash
xcode-select --install
```

If it answers that the software "is not currently available", the tools are
already there. Close the terminal, open a new one, and run `git --version` again.

### Python 3.11 or later

```bash
python3 --version
```

macOS ships a `python3`, but which version depends on your macOS release and it
is often older than 3.11. If yours is below 3.11, get the current release from
[python.org/downloads](https://www.python.org/downloads/) — take the macOS
64-bit universal2 installer, click through it, then **open a new terminal** and
check again. No Homebrew, no pyenv, no virtual environment. This repo has zero
third-party dependencies, so a plain system Python is all it wants.

### Windows and Linux

**Windows:** install git from [git-scm.com/download/win](https://git-scm.com/download/win)
and Python from [python.org](https://www.python.org/downloads/). In the Python
installer, tick **Add python.exe to PATH** on the first screen — missing that box
is the single most common Windows problem, and it makes `python3` fail with
"not recognized" later.

**Linux:** your package manager has both. On Debian or Ubuntu,
`sudo apt install git python3`.

---

## Setup, from nothing

You do not need to know how to code. You need a terminal, about ten minutes, and
a Canvas account.

### 1. Open a terminal

**Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
**Windows:** press the Start key, type `PowerShell`, press Enter.

### 2. Install Claude Code

**Mac / Linux / WSL**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows PowerShell**

```powershell
irm https://claude.ai/install.ps1 | iex
```

Close the terminal and open a new one, then check it worked:

```bash
claude --version
```

You should see a version number. If you get `command not found`, **close the
terminal completely and open a new one** — the installer adds `claude` to a path
your current window loaded before it existed. Anything else, see
[docs/troubleshooting.md](docs/troubleshooting.md).

### 3. Log in

```bash
claude
```

This opens your browser to sign in. Claude Code needs a Pro, Max, Team, or
Enterprise plan; the free Claude.ai tier does not include it. Once you are signed
in, type `/exit` to come back to the terminal.

### 4. Get your Canvas access token

1. Open Canvas
2. Click **Account** in the far-left sidebar, then **Settings**
3. **Scroll all the way down** to the **Approved Integrations** section
4. Press **+ New Access Token**
5. Give it a purpose like `academics-agents`. Leave the expiry date **blank** so
   it does not stop working mid-semester. Press **Generate Token**
6. **Copy it right now.** Canvas shows the token exactly once and there is no way
   to see it again. If you lose it, delete that entry and generate a new one.

You also need your Canvas web address — whatever is in the browser bar, for
example `https://myschool.instructure.com`.

### 5. Get the code and add your token

```bash
git clone https://github.com/HenryVantieghem/academics-agents.git
cd academics-agents
```

Now run the setup helper. It asks for your Canvas address and token, checks the
token against Canvas straight away, and writes the `.env` file for you:

```bash
python3 scripts/init.py
```

Your token stays hidden while you type it, and the file is written owner-only.
If the token is wrong you find out immediately, rather than three steps later.

<details>
<summary><b>Prefer to do it without the helper?</b></summary>

**One line, prompts you for both values** (Mac / Linux):

```bash
read -p "Canvas URL: " u && read -s -p "Token: " t && printf 'CANVAS_BASE_URL=%s\nCANVAS_TOKEN=%s\n' "$u" "$t" > .env && chmod 600 .env && echo " saved"
```

Windows PowerShell:

```powershell
$u = Read-Host "Canvas URL"; $t = Read-Host "Token" -AsSecureString
"CANVAS_BASE_URL=$u`nCANVAS_TOKEN=$([Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($t)))" | Set-Content .env
```

**Or by hand:** copy `.env.example` to `.env` and fill in the two values in any
text editor.

Both work, but neither checks the token. A bad paste fails later during harvest
instead of immediately, which is the main reason `init.py` exists.

</details>

`.env` is gitignored however you create it, so your token never gets committed,
and the scripts read it automatically — there is nothing to `source` or `export`.

### 6. Build everything

```bash
python3 scripts/setup.py
```

That discovers your courses, creates a folder per class, harvests everything
Canvas exposes, records a baseline for change detection, and prints your
dashboard. It takes a minute or two depending on how many courses you have.

### 7. Hand the agent the prompt

```bash
claude
```

Then paste the prompt in the next section. `setup.py` deliberately leaves the
per-course files as **stubs full of `UNKNOWN` markers** — turning those into real
expertise means reading each syllabus and deciding what matters, which a script
cannot do and should not fake.

## The bootstrap prompt

Paste this into Claude Code (or any coding agent) from inside the repo:

````text
You are setting up my academics command centre in this repository.

SETUP
1. Confirm .env has CANVAS_BASE_URL and CANVAS_TOKEN, then run:
      python3 scripts/setup.py
   (The scripts read .env themselves — nothing needs sourcing or exporting.)
   If a step fails, fix it and re-run — every step is idempotent.

2. Read SKILL.md and docs/assignment-production.md before doing anything else.

FOR EACH COURSE in data/courses.json, build real context:

3. Read everything harvested for it:
      courses/<CODE>/_canvas/INDEX.md      what exists and what Canvas refused
      courses/<CODE>/_canvas/MODULES.md    the instructor's own ordering
      courses/<CODE>/_canvas/assignments/  every assignment with its rubric
      courses/<CODE>/files/                syllabus and handouts

   The syllabus is the highest-authority document. Find it and read it in full.
   Assignment PDFs frequently hide data in embedded images that NO text extractor
   returns — if prose references a table or figure you cannot see, run
   `pdfimages -png` and look at it. Never fill a missing given from memory of a
   textbook.

4. Fill in courses/<CODE>/00-context/COURSE-CONTEXT.md. Replace every UNKNOWN
   with a fact AND its source. Where a source is genuinely silent, leave
   "UNKNOWN — not stated in <file>". A marked gap is useful; a confident guess is
   worse than nothing. Pay particular attention to:
     - grading weights, and whether Canvas's assignment-group weights AGREE with
       the syllabus (they often do not — the syllabus governs, and every
       Canvas-computed running grade is wrong until the instructor fixes it)
     - for each assignment type, whether it is graded on CORRECTNESS or on
       COMPLETION, quoted verbatim — they demand completely different artifacts
     - the instructor's policy on collaboration, outside resources, and AI. Quote
       it exactly. These policies are usually split by assessment type, and the
       split is load-bearing.
     - submission routing and required file formats

5. Fill in courses/<CODE>/00-context/SKILL.md — the sub-skill. Beyond the facts,
   build the SUBJECT-MATTER section: the topics in teaching order, the technique
   for each, and the common failure modes. Tag every topic [SCHEDULED] (has a
   schedule row), [NAMED] (in the objectives, no schedule row), or [ASSUMED]
   (standard background, not evidenced). That distinction separates "will be
   assessed" from "might get mentioned."

6. Write data/SCHEDULE.md: one term-wide table of every dated assessment across
   all courses, sorted by date, each row carrying course, item, points, and
   submission route. Then flag the crunch weeks where several land together.

VERIFY BEFORE REPORTING
7. Run `python3 scripts/dashboard.py --days 30` and check your work against it.
   State explicitly which courses it cannot see (no Canvas shell, or nothing
   published) — a clean report that omits them is misleading.

RULES
- Never state a deadline from memory. Run refresh.py then dashboard.py.
- Never invent a fact about a course. Mark it UNKNOWN and say which file was silent.
- Do not submit anything. Submission is mine.
- Follow each instructor's stated policy on outside help, per assessment type.
````

---

---

## Using Cursor instead of Claude Code

Everything above holds; only steps 2, 3 and 7 change. The repo is plain Python
and plain markdown, so any coding agent that can read files and run terminal
commands can drive it.

### 1. Install Cursor

Download it from [cursor.com](https://cursor.com), drag it to Applications, and
sign in when it opens. **Skip steps 2 and 3 above** — you do not need Claude Code
installed at all.

### 2. Do steps 4, 5 and 6 exactly as written

Generate your Canvas token, clone the repo, run `init.py`, run `setup.py`.
Cursor has a built-in terminal (**Terminal → New Terminal**, or Ctrl + `` ` ``)
and every command above runs there unchanged.

### 3. Open the folder, not a file

**File → Open Folder**, then choose the `academics-agents` folder you cloned.

Open the folder itself. The agent only sees what is in the open workspace, and
opening a single file instead is the most common reason it reports that it cannot
find `scripts/setup.py`.

### 4. Use Agent mode, not Ask mode

Open the chat pane and switch the mode selector to **Agent**. Agent is the mode
allowed to edit files and run commands; Ask can read but cannot write, so the
setup appears to be working and then produces nothing.

### 5. Paste the bootstrap prompt

The same [bootstrap prompt](#the-bootstrap-prompt) as above, unchanged.

Cursor asks you to approve each terminal command it wants to run. Approve them —
they are the `python3 scripts/*.py` calls already listed in this README. If
clicking through each one gets tedious you can allowlist `python3` in the agent's
terminal settings, but read what you are allowing before you do.

### What makes it behave

This repo ships [`.cursor/rules/academics-agents.mdc`](.cursor/rules/academics-agents.mdc).
Cursor loads it automatically whenever the folder is open, and it points the agent
at `SKILL.md` — the same operating rules Claude Code reads. That is what keeps
both agents honest about the two that matter: never state a deadline from memory,
and never invent a fact about a course.

### Other agents

Nothing else here is agent-specific. Codex, Windsurf, Zed, and Copilot agent mode
all work through the same three ingredients: an open folder, terminal access, and
the bootstrap prompt. If your agent has a project-rules mechanism, point it at
`SKILL.md` the way the Cursor rule does.

## Daily use

```bash
cd academics-agents
python3 scripts/refresh.py       # what changed — read this first
python3 scripts/dashboard.py     # what is due
```

The scripts read `.env` themselves, so there is nothing to source or export. That
is deliberate: `set -a && source .env` is bash-only, and on Windows PowerShell it
fails with a confusing "CANVAS_TOKEN is not set" on a token you just pasted.

| Script | What it does |
|---|---|
| `init.py` | asks for your Canvas address and token, verifies it, writes `.env` |
| `setup.py` | runs `init.py` if needed, then discover → scaffold → harvest → baseline → dashboard |
| `discover.py` | active enrollments → `data/courses.json` |
| `harvest.py` | all Canvas content → markdown; downloads files |
| `scaffold.py` | per-course folders + context/skill stubs (never overwrites) |
| `refresh.py` | re-pull and **diff**, leading with moved due dates |
| `dashboard.py` | grades, overdue, upcoming, and what it cannot see |

---

## Design notes

**Pagination.** Canvas returns 10 items and truncates silently. Every list call
follows the RFC-5988 `Link: rel="next"` header. Integrations that skip this
under-report for months without an error.

**401 ≠ 403.** A 401 is your token. A 403 almost always means the course hides
that endpoint from students — Files is the usual one. Conflating them sends you
chasing a credential problem that does not exist, so they are reported differently.

**Timezones.** Canvas returns UTC. Deadlines convert to the zone Canvas itself
reports for your account; if that lookup fails the tool says so loudly rather
than quietly showing you the wrong hour.

**Stubs, not guesses.** Scaffolding writes `UNKNOWN` markers rather than
plausible defaults. A wrong exam date asserted confidently is worse than a blank.

---

## Scope

Supports learning: deadline tracking, organising material, study guides, practice
problems, working past exams, checking your own draft against the rubric, and
drafting messages to instructors.

Does not style generated work to read as hand-produced, and does not move
material past exam-lockdown controls.

**Your instructor's policy overrides everything here.** Rules on outside help are
often split by assessment type — permitted on a project, forbidden on a quiz.
Record the exact wording in the course context and follow it. Nothing in this
repo submits anything; that is your action.

## Documentation

| File | What is in it |
|---|---|
| [SKILL.md](SKILL.md) | The agent's operating instructions — refresh first, reporting rules, scope |
| [docs/assignment-production.md](docs/assignment-production.md) | How to produce a graded artifact without the eight failure modes that cost marks |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Every error message, matched to its fix |
| [templates/](templates/) | The course-context and sub-skill stubs the agent fills in |
| [.cursor/rules/](.cursor/rules/) | Project rule so Cursor's agent loads `SKILL.md` automatically |

## Contributing

Issues and pull requests welcome. The engine is deliberately stdlib-only — please
do not add a dependency without a strong reason, since the zero-install property
is most of why this is usable by non-programmers.

## License

MIT — see [LICENSE](LICENSE).
