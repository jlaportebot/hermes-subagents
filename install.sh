#!/usr/bin/env bash
# Install the hermes-subagents skill for Claude Code (user scope) and put `hsa` on PATH.
#   ./install.sh            symlink (updates follow `git pull`)
#   ./install.sh --copy     copy instead of symlink
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/skill/hermes-subagents"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/hermes-subagents"
BIN_DIR="${HSA_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$(dirname "$DEST")" "$BIN_DIR"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then rm -rf "$DEST"; fi
if [ "${1:-}" = "--copy" ]; then cp -r "$SRC" "$DEST"; else ln -s "$SRC" "$DEST"; fi
chmod +x "$DEST/bin/hsa"
ln -sf "$DEST/bin/hsa" "$BIN_DIR/hsa"
echo "skill  -> $DEST"
echo "hsa    -> $BIN_DIR/hsa"
command -v hermes >/dev/null || echo "warning: 'hermes' is not on PATH; install Hermes Agent first"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "warning: add $BIN_DIR to PATH";; esac
