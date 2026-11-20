# Reviewing a Hermes worker's result

The worker's report is a **claim**, not evidence. Your job is to confirm the claim at the lowest token cost.

## 1. Machine checks first (near-zero tokens)
```bash
hsa review <id>          # state, exit reason, commits, diffstat, red flags, uncommitted files, report check, report
hsa report <id>          # just the worker's structured report (recovered from the session if it got buried)
hsa verify <id>          # re-runs the acceptance script YOU wrote — the only result you should trust
```
Stop and act if any of these are true:
| Signal | Meaning | Action |
|---|---|---|
| `state=crashed` / `failed` / exit reason `guardrail_halt`, `max_turns`, budget timeout | the run did not finish | `hsa tail <id> -n 30` to see where it stuck, then follow-up or re-brief |
| `STATUS: BLOCKED` | worker hit a wall honestly | read its hypothesis; answer with a follow-up containing the missing fact/code |
| verify FAIL but report says DONE | false claim | `hsa followup` with the failing output (or `hsa loop`) |
| commits `(none)` but report lists changes | forgot to commit, or edited elsewhere | check `uncommitted`; check other dirs it may have touched |
| `report missing headings` | report incomplete (often after a Hermes "evidence" nudge) | `hsa followup <id> "Give your final report again, all six headings"` — cheap, no code changes |
| red flags (TODO, debug prints) | quality miss | follow-up: "remove X at file:line" |
| diffstat touches files outside the brief's allowed list | scope creep | `git diff <base> -- <file>`; revert or follow-up |

## 2. Read the diff — targeted, not wholesale
- `git -C <wd> diff <base> --stat` first; then read only the hunks in the core files:
  `git -C <wd> diff <base> -- <core-file> | head -200`.
- Check: does it actually implement the brief (not a stub, not a special-case that games the test)?
  Did it weaken/delete tests or assertions to pass? Hard-coded expected values? Swallowed errors?
- For bug fixes, confirm the new test fails on the base: `git stash`-free way:
  `git -C <wd> worktree add ../chk <base> && cp <new test> ../chk/... && run` — or just trust `hsa verify` if your
  verify script already includes a regression check.

## 3. Decide
- **Accept**: merge the branch (`git merge --no-ff` or squash), re-run the full suite on the merge result,
  remove the worktree (`git worktree remove <wd>`).
- **Iterate**: `hsa followup <id> "…precise correction with file:line and expected result…"` — same session,
  it keeps its context. Prefer this over a new run.
- **Re-brief**: if two follow-ups did not converge, the brief was wrong or too big. Split it, add the missing
  code/context inline, dispatch fresh (`--force` to reuse the id or a new id).
- **Do it yourself**: if the remaining fix is a few lines and you already know them, that is cheaper than
  another 10-minute worker round.

## 4. Never
- Never report a worker's numbers to the user without having re-run at least the acceptance check yourself.
- Never merge two workers' branches without re-running tests on the combined result.
