---
name: course-{{CODE}}
description: "{{CODE}} ({{NAME}}) — load for anything about this course: deadlines, assignments, exams, study material, the syllabus, or subject matter."
---

# {{CODE}} — {{NAME}}

> **STUB.** Fill this in from `COURSE-CONTEXT.md` and the harvested Canvas
> material. This file is the routing layer: what to read, in what order, and the
> traps specific to this course.

## Fast facts

| | |
|---|---|
| Canvas | {{CANVAS_URL}} |
| Instructor | {{TEACHERS}} |
| Term | {{TERM}} |
| Meets | UNKNOWN |

## Reading order for a question about this course

1. `courses/{{CODE}}/00-context/COURSE-CONTEXT.md` — the hand-built reference
2. `courses/{{CODE}}/_canvas/assignments/<name>.md` — the specific item
3. The syllabus PDF in `courses/{{CODE}}/01-syllabus/` — only if the first two miss

**Never answer a deadline question from this file.** Run
`python3 scripts/refresh.py && python3 scripts/dashboard.py`. Dates move.

## Subject matter

UNKNOWN — the topics this course actually covers, in teaching order, with the
techniques and the common failure modes for each. This is the part that makes the
sub-skill worth having; build it from the lecture material and past assessments.

Tag each topic with its evidence:
- **[SCHEDULED]** it has a row in the syllabus schedule — guaranteed lecture time
- **[NAMED]** it appears in the objectives but has no schedule row
- **[ASSUMED]** standard background, not evidenced in any course document

The distinction is not cosmetic: it is the difference between "will be assessed"
and "might get mentioned."

## What is explicitly NOT in this course

UNKNOWN — worth stating so you do not over-prepare.

## Traps

UNKNOWN — the things that have already cost time or marks here. Append as found.
