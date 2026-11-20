---
name: hermes-subagents
description: Use Hermes Agent (NousResearch hermes-agent CLI) workers as subagents instead of Claude subagents, so Claude only plans, briefs, monitors and verifies while Hermes does the implementation on its own (free/cheap) model. Use when the user asks to "use hermes subagents/workers", "delegate to hermes", "save Claude tokens/usage", or to run many implementation tasks in parallel with Claude as orchestrator. Covers writing briefs, dispatching parallel workers in isolated git worktrees, live monitoring, multi-turn follow-ups, automatic verify-and-fix loops, and reviewing results.
---

# Hermes workers, Claude orchestrator

**Division of labour.** You (Claude) think: decompose, write precise briefs, write acceptance checks, review.
Hermes does: reading the code it needs, editing, running builds/tests, iterating on failures, committing.
Every Hermes step is free to you; every line you read costs you. So: **rich briefs in, compact reports out,
machine verification in between.**

All control goes through one CLI: `bin/hsa` in this skill (`SKILL_DIR/bin/hsa`; install puts it on PATH).

| command | use |
|---|---|
| `hsa doctor` | once per session: setup + hosting mode + latency |
| `hsa worktree <repo> <branch> [--base REF]` | isolated worktree per worker (prints its path) |
| `hsa dispatch <id> <workdir> <brief.md> --verify <verify.sh> --coding` | start a worker (returns at once) |
| `hsa wait <id>… [--any] [--timeout S]` | block until workers finish (run in background to be notified) |
| `hsa loop <id> [--max-fixes N]` | wait → verify → feed failures back → repeat until green |
| `hsa status [--active]` · `hsa tail <id> [-n N]` | live table · latest tool calls of one worker |
| `hsa followup <id> "msg" \| -f file` | next turn in the same Hermes session |
| `hsa verify <id>` · `hsa review <id>` · `hsa report <id>` | your check · compact review packet · just the report |
| `hsa stop <id>` | kill the client + this worker's own commands (session-tagged); may leave a `ghost` turn on gateway Hermes |

## Before the first dispatch (once per session)
```bash
hsa doctor        # hermes found? session store readable? + one tiny real run (free, ~10 s–3 min)
```
It reports latency, whether the client's env reaches workers, and whether turns run in a Hermes **gateway**
(then `hsa stop` cannot end a turn server-side and `--terminal-timeout` has no effect — workers use
background commands instead). If the probe fails, read `references/troubleshooting.md`; don't start a
campaign on a broken setup. `hsa doctor --no-probe` skips the model call.

## The loop
1. **Plan** (you): split the work into tasks of one coherent change each, each with a runnable acceptance check.
   Mark which are independent (parallel) and which depend on others (sequential).
   **Each task's acceptance must be passable on its own branch.** Run the test suite on the base first; if
   something already fails there (e.g. a bug another parallel task is fixing), scope or deselect it in that
   task's brief and verify script — otherwise the worker "fixes" the other task's bug and the merges collide.
2. **Isolate**: one git worktree per parallel task — never two workers in one directory.
   `WD=$(hsa worktree <repo> hsa/<task-id>)` → creates branch `hsa/<task-id>` from HEAD (or `--base REF`) in a
   worktree next to the repo (`../wt-hsa-<task-id>`) and prints its path.
3. **Brief**: write `<brief>.md` from `references/brief-template.md` — every section, even for small tasks:
   Goal, Context (files + line ranges, **pasted code excerpt** of what changes, current vs expected output,
   conventions), What to do (tests first), Constraints (allowed files), Acceptance (exact commands + expected
   output), Report. Read the relevant code yourself with `sed -n` once and paste it; that one read saves the
   worker 3–10 exploration calls of 30–600 s each. Hermes loops when left to explore big files.
   Write `verify.sh` (bash, run with cwd = the worktree and `HSA_WORKDIR`/`HSA_BASE` set; exit 0 = pass) that
   proves acceptance; it is your source of truth. Workers also run it by hand, so never fall back to `main`
   for the base (it moves when sibling branches merge): `BASE=${HSA_BASE:-<base sha>}`.
   Keep briefs and verify scripts outside the worktree (e.g. a campaign dir) so the worker can't "fix" them.
4. **Dispatch** (returns immediately; the worker runs detached in its own session):
   `hsa dispatch <id> "$WD" <brief>.md --verify <verify.sh> --coding`
   `--coding` (recommended for implementation) limits Hermes to terminal/file/code/web/todo tools: half the
   prompt per model call (12.5K vs 26K tokens measured) and no side effects on Hermes' own memory/skills.
   Wall time is dominated by provider latency (30 s to 17 min per call depending on load), not tool count.
   Other options: `-r low|medium|high|xhigh` (default high), `--budget SECONDS` per turn (default 3 h; a
   client-side cap, see troubleshooting), `--terminal-timeout S` (in-process Hermes only),
   `--verify-timeout S` (default 1800 s per verify run), `-m MODEL`, `--clean` (skip AGENTS.md/memory
   injection), `--skills a,b` to preload Hermes skills.
5. **Monitor without spending tokens**: start ONE background waiter and get on with other work:
   `hsa wait id1 id2 id3 --any` with `run_in_background: true` → you are notified when any finishes.
   Or `hsa loop <id> --max-fixes 3` in the background: waits, runs verify, and on failure automatically sends
   the failure output back to the worker as a follow-up turn — the cheapest way to get to green. Its last line
   is `LOOP PASS: …` (exit 0) or `LOOP FAIL: …` (exit 1); exit 2 = it needs you (stopped/ghost worker, no
   verify script). It never restarts a stopped worker.
   Use `run_in_background: true` for waiters from the first call: long foreground commands may be moved to the
   background anyway, and `sleep` polling may be blocked. Only with no background notifications at all
   (headless/print mode), block in chunks below your Bash tool timeout (set it to 600 s):
   `hsa wait id1 id2 --any --timeout 540` — exit 0 = something finished, non-zero = still running, call again.
   Never end your turn while workers you still need are running unless the user asked you to stop.
   Peek only when needed: `hsa status` (table: state, api calls, idle time, last activity), `hsa tail <id> -n 15`
   (last tool calls). An `idle` over ~10 min while `running` usually means a slow provider call, not a hang;
   over ~30 min, check `hsa tail`.
6. **Interact**: workers are multi-turn. After a turn ends, `hsa followup <id> "<message>"` (or `-f file.md`)
   resumes the *same* Hermes session with full context: corrections, next phase, "explain X", "also do Y".
   Turns can't be steered mid-flight. Prefer letting a turn finish and correcting it with a follow-up:
   `hsa stop` kills the client and the worker's own session-tagged commands, but with a gateway-hosted Hermes
   the turn itself can keep going server-side (`hsa status` then shows `ghost`; see troubleshooting; `hsa stop`
   again sweeps what it restarts) — wait for it to end before reusing the worktree. A follow-up sent meanwhile
   is queued and runs after the ghost turn.
7. **Review**: `hsa review <id>` (one compact packet) + `hsa verify <id>`; then follow
   `references/review-checklist.md`. Read only the core hunks of the diff. Never relay unverified claims.
   With Hermes' `agent.verify_on_stop` on (off by default) a worker can stay `running` for minutes after it
   reported, answering Hermes' evidence nudges: once `hsa report <id>` starts with `STATUS: DONE` and
   `hsa verify <id>` passes, review and merge its commits; remove the worktree only after the turn ends.
8. **Integrate**: merge accepted branches one at a time, re-run the full test suite on the result, remove
   worktrees (`git worktree remove`). Report to the user with *your* verification output.

## Parallelism
- 3–4 concurrent workers is a good default; the model provider rate-limits and the machine's CPU is shared
  (builds/tests from parallel workers compete). Measured: with ~8 concurrent Hermes sessions on one free
  endpoint, single model calls stretched to 10–17 minutes. Check `hsa status --active` before adding more.
- Dependent tasks: dispatch B after A is accepted and merged; base B's worktree on the merge commit
  (`hsa worktree <repo> hsa/B --base <merge-sha>`).
- While workers run, do your own cheap work: write the next briefs and verify scripts, review finished runs.

## Context and tools for the worker
Hermes is free (or cheap), so over-supply context: it costs you a few hundred tokens to write and saves the worker
dozens of slow exploration steps.
- **In the brief**: the goal, exact files + line ranges, the code excerpt to change, current vs expected
  output, conventions, the acceptance commands, and anything you already learned (failed approaches too).
- **Reference files**: long material (specs, logs, API docs, a previous worker's report) goes in a file next to
  the brief; name it in the brief ("read `/path/spec.md` first"). Don't paste 2,000 lines into the prompt;
  prompts over 100 KB are refused.
- **Project rules**: Hermes auto-loads `AGENTS.md`/`CLAUDE.md`-style files from the workdir, plus its own
  memory and skills. `--clean` turns that off when it is noise (unrelated memories, huge rules files).
- **Tools**: Hermes' default toolsets (terminal, file, code execution, web, browser, its own `delegation`
  subagents…) come from its config. Use `--coding` for implementation, `-t <list>` for a custom set (e.g. add
  `browser` for web-UI work), and `--skills name1,name2` to preload Hermes skills that match the task.
- **Long commands**: the preamble makes workers run anything long (builds, big suites) in the background and
  wait on it with `process_manage`; that works everywhere. `--terminal-timeout` additionally raises Hermes'
  foreground limits, but only when `hsa doctor` says env is forwarded (in-process Hermes). Say in the brief
  when a command is expected to take long, so the worker backgrounds it from the start.
- **Secrets**: never paste tokens into a brief. If the task needs credentials, tell the worker which env var or
  file the tool already reads; the preamble forbids printing them.

## What to give Hermes (and what not)
- Great: implement a specified feature/fix with tests; port/translate code; write tests for given behaviour;
  mechanical refactors with a check; doc writing from given facts; run long builds/benchmarks and report numbers;
  research tasks whose output is a file with a fixed structure.
- Poor: open-ended debugging across a big codebase with no hypothesis; architecture decisions; anything whose
  success can't be checked by a command. Do that analysis yourself, then brief the fix.

## Files
- `bin/hsa` — the CLI. Runs live in `$HSA_RUNS_DIR` (default `~/.local/state/hermes-subagents/runs/<id>/`):
  `meta.json`, `brief.md`, and per turn `turn-N.{prompt,out,err,usage,done,verify}`. `out` = worker's final answer.
- `references/worker-preamble.md` — rules prepended to every brief (scope, safety, anti-loop, git, report format).
  Override with `HSA_PREAMBLE=/path`. Use `--no-preamble` for non-coding tasks.
- `references/brief-template.md` — fill-in brief + sizing rules.
- `references/review-checklist.md` — how to verify and when to iterate / re-brief / do it yourself.
- `references/troubleshooting.md` — slow provider, loops, guardrail halts, stuck runs, stopping, session ids.
