# hermes-subagents

A [Claude Code](https://claude.com/claude-code) skill + a small CLI (`hsa`) that lets Claude act as the
**planner / orchestrator / reviewer** while [Hermes Agent](https://github.com/NousResearch/hermes-agent)
workers do the **implementation**: reading code, editing, building, testing, iterating, committing.

Why: Claude usage is the scarce resource; Hermes can run on free or cheap models. With this skill Claude
spends its tokens on decomposition, precise briefs, and verification — and nothing on the long
edit/test/retry loops.

```
            ┌───────────── Claude (orchestrator) ─────────────┐
            │ plan → brief.md + verify.sh → review → merge      │
            └──────┬──────────────┬──────────────┬─────────────┘
       hsa dispatch│              │              │      hsa wait / loop / review / followup
            ┌──────▼─────┐  ┌─────▼──────┐ ┌─────▼──────┐
            │ Hermes #1  │  │ Hermes #2  │ │ Hermes #3  │   one git worktree each,
            │ worktree A │  │ worktree B │ │ worktree C │   own process group, own session
            └────────────┘  └────────────┘ └────────────┘
```

## What you get
- **`hsa` CLI** (Python 3 stdlib only):

  | command | what it does |
  |---|---|
  | `hsa worktree <repo> <branch>` | create an isolated git worktree for one worker |
  | `hsa dispatch <id> <workdir> <brief.md> --verify verify.sh` | start a worker (detached; returns at once) |
  | `hsa status` | table of all workers: state, API calls, idle time, last activity |
  | `hsa tail <id>` | the worker's latest tool calls / messages, live |
  | `hsa wait <id>... [--any]` | block until workers finish — run it in the background to get notified |
  | `hsa followup <id> "msg"` | next turn in the **same** Hermes session (multi-turn interaction) |
  | `hsa verify <id>` | run *your* acceptance script against the worker's directory |
  | `hsa loop <id> --max-fixes 3` | wait → verify → on failure send the failure back as a follow-up → repeat |
  | `hsa review <id>` | compact review packet: exit reason, commits, diffstat, red flags, final report |
  | `hsa report <id>` | just the worker's structured report (recovered from the session if it got buried) |
  | `hsa stop <id>` | kill the worker's client and its own (session-tagged) commands |
  | `hsa doctor` | setup check + one tiny probe run: latency, env forwarding, gateway vs in-process |

- **The skill** (`skill/hermes-subagents/SKILL.md`): the orchestration workflow Claude follows.
- **Worker preamble** prepended to every brief: scope and git safety, anti-loop rules, quality bar,
  mandatory self-verification, and a fixed report format the orchestrator can check mechanically.
- **Brief template** and **review checklist** distilled from real multi-day campaigns.
- **Evals** (`evals/`): six tasks with hidden tests (bug fix, spec'd feature, mutation-scored test writing,
  multi-turn follow-up, verify-and-fix loop, stop) and a scorer. See `evals/CRITERIA.md` and results below.

## Install
Requirements: Claude Code, Hermes Agent with a working model provider (`hermes -z "say hi"` must work),
git, Python ≥ 3.9, bash. Platform: Linux only (`hsa` reads `/proc`); macOS and Windows are not supported.

```bash
git clone https://github.com/<you>/hermes-subagents && cd hermes-subagents
./install.sh          # symlinks the skill into ~/.claude/skills and hsa into ~/.local/bin
hsa doctor            # checks the setup with one tiny real Hermes run
```
Then in Claude Code: *"use hermes subagents to implement …"*.

Environment knobs: `HSA_RUNS_DIR` (run files, default `~/.local/state/hermes-subagents/runs`),
`HERMES_HOME` (Hermes data dir, default `~/.hermes`; used for live monitoring), `HSA_HERMES_BIN`,
`HSA_PREAMBLE` (custom worker rules).

## Quick example
```bash
WD=$(hsa worktree ~/src/myproj hsa/fix-parser)
hsa dispatch fix-parser "$WD" briefs/fix-parser.md --verify briefs/fix-parser.verify.sh --coding
hsa loop fix-parser --max-fixes 3   # Claude runs this with run_in_background; exit 0 = verified
hsa status
hsa review fix-parser
```

## How it works
- Each worker is `hermes -z <preamble + brief> --in <workdir> --yolo --usage-file …` in its own process
  session under `timeout`; a wrapper writes a `done` marker with the exit code. `--coding` restricts
  Hermes to terminal/file/code/web/todo tools (half the prompt per call, no writes to Hermes' memory/skills).
- Follow-ups run `hermes -z <message> --resume <session-id>`, so the worker keeps its full context.
- Live monitoring reads Hermes' session store (`$HERMES_HOME/state.db`) read-only.
- Verification is always done by the orchestrator's own script — the worker's report is a claim.
- Files it touches: run files under `HSA_RUNS_DIR`; worktrees you create with `hsa worktree`; `.hsa-tmp/`
  added to the repo's `.git/info/exclude` (local to the clone, never committed); nothing else outside the workdir.

### Gateway-hosted Hermes (important)
Recent Hermes versions execute `hermes -z` turns inside the long-lived Hermes gateway; the CLI process is
only a viewer. Consequences, all measured and handled:
- `hsa stop` kills the client and the worker's own commands (matched by `HERMES_SESSION_ID`; other workers,
  your own sessions and gateway helpers are untouched), but the turn can continue server-side; `hsa status` then shows `ghost` until it ends. Keep tasks small and correct with follow-ups.
- Only an allowlist of client env vars reaches the session, so `--terminal-timeout`/`--budget` are not hard
  limits there. Workers run long commands in the background and wait on them (rule in the preamble).
- A follow-up sent to a busy session is queued, not an interrupt.
`hsa doctor` tells you which mode your install uses.

## Eval results
See [`evals/RESULTS.md`](evals/RESULTS.md).

## Safety notes
Workers run with `--yolo` (no approval prompts) — that is what makes unattended work possible, and it is
also why the preamble forbids pushes, history rewrites, sudo, and touching anything outside the workdir,
and why each worker gets its own worktree. Review before you merge. Don't point workers at directories
containing secrets.

## License
MIT
