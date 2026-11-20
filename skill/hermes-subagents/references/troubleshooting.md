# Troubleshooting Hermes workers

## Setup
- `hermes` not found → install Hermes Agent and make sure the `hermes` CLI is on PATH (or set `HSA_HERMES_BIN`).
- `hsa tail` / `hsa status` show no session or zero calls → `hsa` reads Hermes' session store at
  `$HERMES_HOME/state.db` (default `~/.hermes/state.db`). Set `HERMES_HOME` if Hermes lives elsewhere.
  Monitoring degrades gracefully: `wait`, `verify`, `review` still work from the run files.
- A run ends instantly with `failed` → read `turn-N.err` (`hsa path <id>`): usually provider auth, an
  unknown `-m` model name, or a bad toolset name.

## Slow runs
- Each Hermes step is one model call; on free/shared endpoints a call can take 30–200 s. A 10-step task is
  routinely 10–30 minutes. That is expected — plan in parallel and don't poll.
- `hsa status` column `idle` = time since Hermes last recorded activity. `running` with `idle` < 10 min is
  normal. If `activity` says "waiting for stream response" for a long time the provider is degraded;
  consider `--budget` caps, fewer parallel workers, or a different `-m` model.
- `--budget SECONDS` is a hard wall clock per turn (default 3 h): the run is killed at the limit and the
  turn is marked failed; follow up to continue from where it stopped (the session keeps its history).

## Loops and halts
- `turn_exit_reason: guardrail_halt` (in `hsa review`) = Hermes' own loop detector stopped it, typically after
  re-reading the same big file. Re-brief with the exact code inline and an explicit "edit X at line Y".
- `max_turns` = too many tool iterations in one turn: split the task, or follow up with "continue".
- The worker re-runs a failing command forever → the preamble's anti-loop rule should stop it after two
  attempts; if not, `hsa stop` and follow up with the fix hint.

## Stopping (read this — it is the sharp edge)
- Recent Hermes versions execute a `hermes -z` turn **inside the Hermes gateway**; the `hermes` client process
  is only a viewer. Killing the client does *not* stop the model loop, and the worker's shell commands are
  children of the gateway, not of the client.
- `hsa stop <id>` therefore: sends SIGINT to the client (Hermes' own Ctrl+C path), then SIGTERM/SIGKILL to the
  client tree, then kills every process that a hermes process spawned **inside the worker's workdir** (so
  the running build/test dies). It cannot end the server-side turn itself.
- After a stop, `hsa status` shows `ghost` if the session keeps recording activity. A ghost finishes its
  current turn on its own (it stays confined to its workdir, cannot push). Until it ends: don't reuse that
  worktree and don't send follow-ups. If you must end it now, the session can be interrupted from Hermes'
  own UI (Ctrl+C in an attached TUI) or by restarting the gateway — both are the user's call, because the
  gateway may also serve their chat bots.
- Measured on a gateway-hosted Hermes: after `hsa stop`, the ghost turn noticed its command had died and
  restarted it in the background; a follow-up message sent to the busy session is **queued**, not treated as an
  interrupt — it runs after the ghost turn ends. A queued "STOP — kill your background processes and reply
  `STATUS: STOPPED`" follow-up is still useful: it makes the worker clean up its own background jobs.
- `--budget` has the same limit: it kills the client at the deadline; a gateway-hosted turn may keep running
  until it ends naturally. Hermes' own server-side cap (`agent.run_budget_seconds`, `agent.max_turns`) lives
  in Hermes' global config and affects every session, so it is the user's decision to set it.
- Prevention beats stopping: set `--budget` sensibly, keep tasks small, and prefer letting a run finish and
  then correcting it with `hsa followup`.
- Older Hermes versions run one-shot turns in-process; there `hsa stop` stops everything.

## Side effects on Hermes itself
Hermes learns: with its default toolsets a worker may save memories or create Hermes skills from what it
did (e.g. a throwaway eval task). For implementation workers use `--coding` (terminal, file, code_execution,
web, todo) — it removes memory/skill-authoring/messaging/cron tools, and with fewer tool schemas each model
call is smaller.

## Long commands
Hermes caps foreground commands twice: the terminal tool's timeout (default 180 s, max 600 s) and a
per-tool-batch guard (420 s by default). When Hermes runs turns **in-process**, `hsa dispatch
--terminal-timeout S` raises both through the environment. When turns run in a **gateway** (`hsa doctor`
says so), the gateway only accepts an allowlist of client env vars (PATH and toolchain variables), so those
limits stay at the gateway's own config. The preamble therefore tells every worker to run long commands with
the terminal tool's `background=true` and to `process_manage` `wait` repeatedly until the process exits —
measured: a 10-minute command completed this way with three 180 s waits. Without that rule a worker whose
command gets killed tends to improvise (split the command, write checkpoints) instead of doing the task.

## Hermes' own verification nudges
With `agent.verify_on_stop` enabled in Hermes' config, Hermes injects up to two "[System: … fresh passing
verification evidence]" messages after a turn that edited code, unless it saw the project's detected
full-suite command pass (it detects `pytest` from `pytest.ini`/`[tool.pytest…]`, `npm|pnpm|yarn run test`,
`make test`, `scripts/run_tests.sh`; a run with explicit test targets counts only as "targeted"). Effects:
1–2 extra model calls per turn, and the final answer may become an evidence reply instead of the report.
Mitigations built in: the preamble asks workers to answer an evidence request in one step and then repeat
the report, and `hsa report`/`hsa review` recover the structured report from the session if it got buried.
The setting is global Hermes config (and not forwardable per session), so whether to turn it off is the
user's call.

## Follow-ups
- `hsa followup` needs the Hermes session id, which `hsa` takes from the turn's usage file or, while the
  usage file is not yet written, from `state.db` (matched by working directory + start time — another
  reason for one worker per directory).
- A follow-up is a new turn in the same session: the worker remembers the brief, its edits and outputs.
  Keep follow-ups specific: what is wrong (paste the failing line), what the expected result is.

## Two workers, one directory
Don't. They overwrite each other's edits and `hsa` refuses it unless `--share-workdir`. Use
`hsa worktree <repo> <branch>`; for non-git work, give each worker its own directory.
