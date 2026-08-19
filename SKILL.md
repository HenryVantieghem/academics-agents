---
name: academics
description: "Canvas-backed academic command centre. Use for anything school-related — what is due, overdue work, grades, exam and quiz dates, a specific course, study guides, practice problems, assignment requirements, or the class schedule."
---

# Academics

An agent-operated command centre over a Canvas LMS account. It keeps a local,
readable mirror of every course, tracks what is actually due, and grows a
per-course sub-skill as it learns each class.

**Repo layout**

```
data/courses.json            the course registry — everything reads this
data/last-seen.json          change-detection baseline
courses/<CODE>/
  00-context/COURSE-CONTEXT.md   hand-built reference — read this first
  00-context/SKILL.md            the per-course sub-skill
  _canvas/                       harvested mirror: assignments, pages, quizzes, modules
  01-syllabus/ 02-lectures/ 03-assignments/ 04-exams/ 05-study-guides/ 06-notes/
scripts/                     the engine (stdlib only)
```

## Refresh first, every time

Not optional, and not only when something looks stale. Instructors add
assignments, attach rubrics, and **move due dates** continuously. Answering from
yesterday's snapshot is how a moved deadline gets missed.

```bash
set -a && source .env && set +a
python3 scripts/refresh.py      # ALWAYS first — reports what changed
python3 scripts/dashboard.py    # then answer from this
```

`refresh.py` prints `no changes` in seconds when nothing moved. **Lead your answer
with anything it flagged** — a due date that moved outranks the deadline list.

## Reporting rules

- **Never state a deadline from memory or from a cached file.** Run the dashboard.
- **Say what is not covered.** A course with no Canvas shell, or one that has
  published no assignments, is invisible to the dashboard. A clean report that
  omits this implies nothing is due when the truth is nothing is *visible*.
- **Give the submission route with every item.** `api` can be pushed
  programmatically; `browser` needs the student's own logged-in session
  (Gradescope, publisher tools, quiz engines); `none` is in-class or not collected.
- **In-class items are not submit items.** A quiz on the list means *be in the
  room*, not *upload something*.

## Working an assignment

Read `docs/assignment-production.md` before generating anything that will be
submitted, printed, or studied from. The short version:

1. **Read the grading contract before the problems.** Correctness-graded and
   completion-graded work need different artifacts.
2. **Do not trust a text extractor on an assignment PDF.** Tables are often
   embedded images invisible to every extractor, and exponents can be flattened
   into products.
3. **Verify numerically in code** before showing anyone an answer.
4. **Check the built document, not just the exit code.** Renderers report success
   on visibly broken output.
5. **Have a second agent grade it adversarially**, and pin the file's identity in
   the request so you do not get a verdict on a stale build.

## Scope

This supports learning: tracking deadlines, organising material, building study
guides and practice problems, working past exams, checking a draft against the
rubric, and drafting messages to instructors.

It does not style generated work to read as hand-produced, and it does not move
material past exam-lockdown controls.

**Honour the course's own policy above all of this.** Instructors' rules on
outside help are frequently split by assessment type — permitted on a project,
forbidden on a quiz — and that split is the whole point. Record the exact wording
in the course context and follow it.

**Nothing here submits anything.** Submission is the student's action.
