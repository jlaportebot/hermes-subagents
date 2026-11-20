# Brief template for a Hermes worker

Copy this, fill every section, delete nothing. The brief is the worker's entire world: Hermes cannot see your
conversation, and every exploration step it takes costs minutes. Because Hermes tokens are free and yours are
not, **put context in the brief** (exact paths, line ranges, code excerpts, commands, expected output) instead of
asking the worker to discover it. A long, precise brief is cheap; a vague one costs a failed run and your review.

---

```markdown
# <TASK-ID>: <one-line imperative title>

## Goal
<2–4 sentences: what must be true when done, and why it matters. One task per brief.>

## Context you need (do not re-discover this)
- Repo: <what the project is, language, how it is laid out — 3–6 lines>
- Relevant files (read only these unless something is missing):
  - `<path>:<start>-<end>` — <what is there>
  - `<path>` — <what is there>
- Current behaviour: <exact observed output / error, copied verbatim>
- Root cause (if known): <your analysis, with the exact code involved>
- Exact code involved (paste it — this is the single biggest time saver):
  ```<lang>
  <the 10–80 lines the worker must change, with their file:line>
  ```
- Conventions: <naming, error handling, test framework, how tests are named, commit trailer if special>

## What to do
1. <concrete step — e.g. "In `src/x.py:120-140`, change `parse()` so that …">
2. <write the failing test first: file, test name, what it asserts>
3. <implement>
4. <run acceptance>

## Constraints
- Allowed to edit: <paths/globs>. Do NOT edit: <paths>.
- <performance / API compatibility / no new dependencies / etc.>

## Acceptance (the orchestrator will re-run exactly these)
- `<command 1>` → exit 0 and output contains `<expected text>`
- `<command 2>` → exit 0
- Verify script: `<path/to/verify.sh>` (if dispatched with --verify)

## Report
Use the STATUS / COMMITS / CHANGES / ACCEPTANCE / TESTS ADDED / NOT DONE format from your rules.
<Add any task-specific items you want in the report, e.g. "the measured latency before/after".>
```

---

## Sizing rules (learned the hard way)
- **One worker = one coherent change** that a single acceptance command can prove (≈ 1–6 files).
  Split bigger work into sequential or parallel briefs.
- Analysis-heavy, open-ended "figure out why" work over large unfamiliar code is where Hermes loops
  (re-reads the same 2,000-line file until a guardrail halts it). Do the analysis yourself (cheaply, with
  `grep`/`sed -n` on just the hot spot), then hand Hermes the exact change. Or give Hermes a pure
  **research brief** whose deliverable is a written report file, with explicit files to read and a cap
  ("read at most these 5 files; write findings to `.hsa-tmp/report.md`").
- Acceptance must pass on the task's own branch. If the base already has failing tests unrelated to this
  task (or fixed by a parallel task), deselect them explicitly in the acceptance command and say why.
- Always give a runnable acceptance check. "Make it better" cannot be verified; "`pytest -q tests/test_x.py`
  passes and prints `5 passed`" can.
- If the task needs a long build/test (> 3 min), say so in the brief and dispatch with a higher
  `--terminal-timeout` so Hermes' foreground commands are not cut off.
