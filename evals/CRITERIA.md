# Eval criteria

The eval measures whether the skill lets a Claude orchestrator get correct, verifiable work out of Hermes
workers cheaply. Fixture: `fixture/` (a tiny Python package with a planted bug). Each task runs in its own
git worktree, in parallel, through `hsa`. Hidden tests live in `tasks/<t>/hidden_test.py` and are never
visible to the worker; `verify.py` copies the worktree to a temp dir, adds the hidden test and runs pytest
(T3 is mutation-tested instead: the worker's tests must kill all 7 mutants of `stats.py`).

## Per-task criteria (scored by `score.py`, 7 points)
| criterion | pass condition |
|---|---|
| pass | hidden acceptance check exits 0 |
| honest | the report says `STATUS: DONE` exactly when the hidden check passes |
| scope_ok | every file changed vs `main` is in the task's `allowed` list |
| clean_tree | `git status --short` empty at the end (no stray files) |
| committed | ≥ 1 commit on the task branch, with the Hermes `Co-Authored-By` trailer |
| report_format | final answer has all six headings of the preamble's report format |
| no_red_flags | no TODO/FIXME/print/breakpoint added |

Also recorded: turns, API calls, minutes, exit reason, size of the `hsa review` packet (proxy for the
orchestrator tokens a review costs).

## Tasks
| task | what it exercises |
|---|---|
| t1-bugfix | bug fix with regression tests; brief with exact code |
| t2-feature | spec-table feature with strict errors; parametrized tests |
| t3-tests | test-writing quality (mutation score), must not touch source |
| t4-multiturn | `hsa followup`: phase 2 refers to "the function you just added" — needs session memory |
| t5-loop | hidden test requires a `unit="seconds"` option the brief never mentions; `hsa loop` must feed the failure back until green |
| t6-stop | `hsa stop` on a worker running a long foreground command: no leftover processes; a server-side turn that keeps going is reported as `ghost`; a second `hsa stop` sweeps commands the ghost restarted |

## Tool criteria (checked by the orchestrator during the run)
- 5+ workers dispatch concurrently without interfering (separate worktrees, correct session matching).
- `status`, `tail` show live progress; `wait --any` notifies on the first finish.
- `followup` resumes the same session id; `loop` converges within `--max-fixes`.
- `stop` leaves no worker process or workdir command running; on in-process Hermes the session stops, on
  gateway-hosted Hermes a continuing turn must be flagged `ghost` by `hsa status` (it cannot be ended
  client-side).

## Target
All tasks 7/7 on the final skill version, with no orchestrator file reads beyond `hsa review` output and
targeted diff hunks; plus an end-to-end run where a fresh Claude session uses only the skill.

## Running it
```bash
evals/run-round.sh /path/to/new-workspace --coding     # ~30-60 min, needs a working `hermes`
```
The workspace must not exist yet; results are printed and saved to `evals/results/<timestamp>.json`.
