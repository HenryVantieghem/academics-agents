# academics-agents

**An agent-operated command centre for your coursework, backed by the Canvas LMS API.**

Point it at your Canvas account and it builds a local, readable mirror of every
class you are enrolled in — assignments, quizzes, pages, modules, files — then
grows a per-course sub-skill so an AI agent actually knows your classes instead
of guessing about them.

Zero third-party dependencies. Python 3.11+ and a Canvas token, nothing else.

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

## Setup

### 1. Get a Canvas token

Your Canvas → **Account → Settings → Approved Integrations → + New Access Token**.
Copy it immediately; Canvas shows it once.

### 2. Configure

```bash
git clone https://github.com/HenryVantieghem/academics-agents.git
cd academics-agents
cp .env.example .env
$EDITOR .env          # CANVAS_BASE_URL and CANVAS_TOKEN
```

### 3. Build everything

```bash
set -a && source .env && set +a
python3 scripts/setup.py
```

That discovers your courses, creates the folder tree, harvests all Canvas
content, records a change baseline, and prints your dashboard.

### 4. Hand the agent the prompt below

`setup.py` leaves the per-course files as **stubs full of `UNKNOWN` markers** —
on purpose. Turning them into real expertise means reading each syllabus and
deciding what matters, which a script cannot do and should not fake.

---

## The bootstrap prompt

Paste this into Claude Code (or any coding agent) from inside the repo:

````text
You are setting up my academics command centre in this repository.

SETUP
1. Confirm .env has CANVAS_BASE_URL and CANVAS_TOKEN, then:
      set -a && source .env && set +a
      python3 scripts/setup.py
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

## Daily use

```bash
set -a && source .env && set +a
python3 scripts/refresh.py       # what changed — read this first
python3 scripts/dashboard.py     # what is due
```

| Script | What it does |
|---|---|
| `setup.py` | discover → scaffold → harvest → baseline → dashboard |
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

## License

MIT — see [LICENSE](LICENSE).
