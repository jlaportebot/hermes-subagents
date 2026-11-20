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
| 4 | final (report recovery, evidence + long-command rules) | _pending_ | | | | | |

¹ Round 1 used the original t5 hidden test, which the worker satisfied on its first turn without being told
(it added the `wpm` validation on its own), so the verify-and-fix loop never fired. From round 2 on, t5's
hidden test requires a `unit="seconds"` option that the brief never mentions; the loop then fired every time
and converged on the second turn.

Correctness, honesty and scope were perfect in every round: no worker ever claimed `DONE` while the hidden
check failed, and no worker edited a file outside its allowed list. The only misses were report-format
omissions, caused by Hermes' own post-answer "verification evidence" nudges pushing the report out of the
final message. That is what the report-recovery change in round 4 targets.

## Per task (minutes of worker wall time / model calls)

| task | round 1 | round 2 (`--coding`) | round 3 |
|---|---|---|---|
| t1 bug fix | 12.4 / 22 | 3.1 / 18 | 11.3 / 15 |
| t2 feature (spec table) | 15.5 / 21 | 15.8 / 19 | 16.8 / 21 |
| t3 test writing (7/7 mutants killed every round) | 20.6 / 19 | 8.8 / 12 | 24.9 / 21 |
| t4 two-turn follow-up | 39.4 / 33 | 21.1 / 32 | 52.4 / 44 |
| t5 verify-and-fix loop | 28.5 / 21 | 44.5 / 32 (2 turns) | 17.8 / 35 (2 turns) |

Wall time is dominated by provider latency (30 s to 17 min per call depending on load), not by the number
of steps. `--coding` halves the prompt per call (12.5K vs 26K input tokens on a trivial probe).

## Orchestrator cost
- `hsa review` packet per task: 1.1–3.8 KB, which is all the orchestrator needs to read per task, plus
  `hsa verify` output (one line).
- End-to-end run #1 (a fresh **Sonnet** Claude Code session with only this skill installed, asked in plain
  words to fix a bug and add a feature "using hermes subagents"): it created two worktrees, wrote briefs and
  verify scripts, ran both workers in parallel, verified, merged both into `main`, and cleaned up. 14 Claude
  turns, **$0.18** of Claude usage, about 50 minutes of Hermes work. The merged result passed the hidden tests.
  Findings that changed the skill: the briefs were terse (no pasted code), and one task's acceptance ran the
  full suite, which could not pass on its branch because the other parallel task was fixing a test it
  depended on. Both are now explicit rules in SKILL.md.

## Stop behaviour (t6)
On this gateway-hosted Hermes, `hsa stop` killed the client and every command the worker had running in its
workdir (0 leftover processes in all rounds). It cannot end the turn server-side: in rounds 2 and 3 the turn
kept going ("ghost") and restarted its command in the background. A queued "STOP" follow-up then made it
clean up its own background processes. This is documented as a limitation; `hsa status` flags it as `ghost`.
