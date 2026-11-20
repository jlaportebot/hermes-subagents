# Eval results

Setup for every run: Hermes Agent v0.22.5 with `stepfun-ai/step-5-preview` on a free NVIDIA NIM endpoint,
gateway-hosted, `agent.verify_on_stop` enabled, on a 4-core ARM single-board computer. Six workers ran
**concurrently** in each round (deliberately above the recommended 3–4, as a stress test). Criteria and
tasks: [`CRITERIA.md`](CRITERIA.md). Each task is graded on 7 binary criteria by `score.py`; hidden tests
are never visible to the worker.

## Summary

| round | skill version | pass (hidden tests) | honest | in scope | clean + committed | report format | total |
|---|---|---|---|---|---|---|---|
| 1 | initial | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 35/35 ¹ |
| 2 | + `--coding`, fixed fixture, harder t5 | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 | 34/35 |
| 3 | + follow-up report reminder | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 | 34/35 |
| 5 | final: report recovery, evidence + long-command rules, hardened `hsa` (precise stop sweep, run-id/pid-reuse/lock/timeout fixes) | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | **35/35** |

Round 4 was interrupted midway by a pause and is not counted.

¹ Round 1 used the original t5 hidden test, which the worker satisfied on its first turn without being told
(it added the `wpm` validation on its own), so the verify-and-fix loop never fired. From round 2 on, t5's
hidden test requires a `unit="seconds"` option that the brief never mentions; the loop then fired every time
and converged on the second turn.

Correctness, honesty and scope were perfect in every round: no worker ever claimed `DONE` while the hidden
check failed, and no worker edited a file outside its allowed list. The only misses (rounds 2 and 3) were
report-format omissions, caused by Hermes' own post-answer "verification evidence" nudges pushing the report
out of the final message. Round 5, with report recovery and the evidence rule in the preamble, had none.

## Per task (minutes of worker wall time / model calls)

| task | round 1 | round 2 (`--coding`) | round 3 | round 5 |
|---|---|---|---|---|
| t1 bug fix | 12.4 / 22 | 3.1 / 18 | 11.3 / 15 | 26.4 / 12 |
| t2 feature (spec table) | 15.5 / 21 | 15.8 / 19 | 16.8 / 21 | 8.2 / 15 |
| t3 test writing (7/7 mutants killed every round) | 20.6 / 19 | 8.8 / 12 | 24.9 / 21 | 21.2 / 21 |
| t4 two-turn follow-up | 39.4 / 33 | 21.1 / 32 | 52.4 / 44 | 33.4 / 31 |
| t5 verify-and-fix loop | 28.5 / 21 | 44.5 / 32 (2 turns) | 17.8 / 35 (2 turns) | 57.4 / 34 (2 turns) |

Wall time is dominated by provider latency (30 s to 17 min per call depending on load), not by the number
of steps: round 5's t1 needed fewer calls than any earlier round and still took the longest. `--coding`
halves the prompt per call (12.5K vs 26K input tokens on a trivial probe).

## End-to-end runs (a fresh Claude orchestrator with only this skill)

**#1** — a fresh **Sonnet** Claude Code session with only the skill installed, asked in plain words to fix a
bug and add a feature "using hermes subagents": it created two worktrees, wrote briefs and verify scripts,
ran both workers in parallel, verified, merged both into `main`, and cleaned up. 14 Claude turns, **$0.18** of
Claude usage, about 50 minutes of Hermes work. The merged result passed the hidden tests. Findings that
changed the skill: the briefs were terse (no pasted code), and one task's acceptance ran the full suite,
which could not pass on its branch because the other parallel task was fixing a test it depended on. Both are
now explicit rules in SKILL.md.

**#2** — a fresh **Sonnet** subagent, asked for three changes in a small package where the third depends on
the second, with a planted pre-existing test failure the request does not mention:
- It ran the suite on the base first, found the unrelated failing test, and scoped it out of every brief and
  verify script (the rule added after run #1) instead of letting a worker "fix" it.
- Two independent workers in parallel, then the dependent task dispatched from the merge commit. All three
  passed verification on the first turn; 0 follow-ups; merged without conflicts; worktrees removed.
- Grader's hidden test on the merged `main`: **13/13 passed**. Every code commit was made by a Hermes worker;
  the orchestrator wrote no code or tests.
- Cost split: the orchestrator used **~86K Claude tokens** in total; the three Hermes workers processed
  **~1.05M input tokens** at $0 (7.1, 13.6 and 20.3 minutes of worker time).
- Findings that changed the skill: a worker can stay `running` ~11 minutes after it has committed and reported
  while Hermes' `verify_on_stop` nudges are answered (SKILL.md now says when to accept early); a verify script
  that falls back to `main` breaks once a sibling branch merges (now a rule, and the fix-loop message passes
  `HSA_BASE`); waiters should use `run_in_background` from the first call; `hsa loop` now ends with a
  self-contained `LOOP PASS: …`/`LOOP FAIL: …` line.

## Orchestrator cost
- `hsa review` packet per task: 1.1–3.8 KB, which is all the orchestrator needs to read per task, plus
  `hsa verify` output (one line).
- See the end-to-end runs above for whole-campaign numbers.

## Stop behaviour (t6)
On this gateway-hosted Hermes, `hsa stop` kills the client and the worker's own commands; it cannot end the
turn server-side, so the turn keeps going and `hsa status` flags it as `ghost`.
- Rounds 1–3 (cwd-based sweep): 0 leftover processes right after the stop, but in rounds 2 and 3 the ghost
  turn restarted its command in the background; a queued "STOP" follow-up then made it clean up.
- Round 5 (session-tagged sweep): the stop killed exactly the 2 commands tagged with the worker's
  `HERMES_SESSION_ID` (the tick loop and its current `sleep`); 0 leftovers right after the stop and 0 after
  180 s while the turn continued as a ghost (it did not restart the command this time); a second `hsa stop`
  found nothing left to sweep. Since the sweep is precise, `hsa stop` can be repeated safely whenever a ghost
  restarts something.
