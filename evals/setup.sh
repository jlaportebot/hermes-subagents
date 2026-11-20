#!/usr/bin/env bash
# setup.sh <workspace>: fresh fixture repo + one worktree and verify.sh per task. Prints nothing on success.
set -euo pipefail
EVALS="$(cd "$(dirname "$0")" && pwd)"
WS="${1:?workspace dir}"
[ -e "$WS" ] && { echo "setup.sh: $WS exists; pick a new workspace" >&2; exit 1; }
mkdir -p "$WS/verify"
cp -r "$EVALS/fixture" "$WS/repo"; find "$WS/repo" -name __pycache__ -prune -exec rm -rf {} +
git -C "$WS/repo" init -q -b main
git -C "$WS/repo" add -A
git -C "$WS/repo" -c user.name=eval -c user.email=eval@example.com commit -q -m "chore: fixture"
for t in "$EVALS"/tasks/*/; do
  name=$(basename "$t")
  git -C "$WS/repo" worktree add -q -b "hsa/$name" "$WS/wt-$name" main
  printf '#!/usr/bin/env bash\nexec python3 %q %q\n' "$EVALS/verify.py" "$name" > "$WS/verify/$name.sh"
done
