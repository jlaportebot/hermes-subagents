#!/usr/bin/env bash
# run-round.sh <workspace> [extra hsa dispatch flags...]
# One full eval round, orchestrated exactly as the skill prescribes, with zero model tokens spent by the
# caller: parallel dispatch of t1..t6 in their own worktrees, verify-and-fix loop on t5, follow-up on t4
# after its first turn, stop test on t6, then score.py. Takes ~30-60 min depending on the provider.
set -uo pipefail
EVALS="$(cd "$(dirname "$0")" && pwd)"
WS="${1:?workspace dir}"; shift
export HSA_RUNS_DIR="$WS/runs"
"$EVALS/setup.sh" "$WS"
log() { echo "$(date +%T) $*"; }
for t in t1-bugfix t2-feature t3-tests t4-multiturn t5-loop t6-stop; do
  hsa dispatch "$t" "$WS/wt-$t" "$EVALS/tasks/$t/brief.md" --verify "$WS/verify/$t.sh" --base main --budget 5400 "$@" | head -1
done
( hsa loop t5-loop --max-fixes 3 > "$WS/t5-loop.log" 2>&1 ) &
( hsa wait t4-multiturn > /dev/null && hsa followup t4-multiturn -f "$EVALS/tasks/t4-multiturn/followup.md" && hsa wait t4-multiturn ) > "$WS/t4.log" 2>&1 &
(
  until hsa tail t6-stop -n 3 | grep -q "CALL terminal"; do sleep 10; done
  sleep 20; log "t6 inside long command; stopping"
  leftovers() { for p in $(pgrep -f 'seq 1 60'); do readlink "/proc/$p/cwd"; done | grep -c wt-t6-stop; }
  hsa stop t6-stop
  echo "leftover tick processes right after stop: $(leftovers)"
  sleep 180
  hsa status t6-stop | tail -1
  echo "leftover tick processes after 180 s (ghost turn may restart them): $(leftovers)"
  hsa stop t6-stop
  sleep 5
  echo "leftover tick processes after a second stop: $(leftovers)"
) > "$WS/t6.log" 2>&1 &
wait
hsa wait t1-bugfix t2-feature t3-tests > /dev/null
log "all workers finished"
cat "$WS/t5-loop.log" "$WS/t6.log"
python3 "$EVALS/score.py" "$WS" "$HSA_RUNS_DIR" t1-bugfix t2-feature t3-tests t4-multiturn t5-loop
