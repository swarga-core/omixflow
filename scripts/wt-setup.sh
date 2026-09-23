#!/usr/bin/env bash
# PostToolUse[EnterWorktree] hook: prepare a freshly created worktree.
# Reads the hook payload from stdin, resolves the worktree dir, initialises
# submodules if the project declares any, then runs `workspace.setup` from
# .claude/omixflow/flow.yaml. Always exits 0: a PostToolUse hook must not block.
#
# Log: ~/.claude/omixflow-wt-setup.log

set -uo pipefail

log="$HOME/.claude/omixflow-wt-setup.log"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

input="$(cat)"
wt="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"
if [ -z "$wt" ] || [ ! -d "$wt" ]; then
  wt="$(printf '%s' "$input" | jq -r '.tool_response.cwd // .tool_input.path // empty' 2>/dev/null)"
fi
if [ -z "$wt" ] || [ ! -d "$wt" ]; then
  echo "$(ts) [wt-setup] no usable worktree path in payload" >> "$log"
  exit 0
fi

cfg="$wt/.claude/omixflow/flow.yaml"
if [ ! -f "$cfg" ]; then
  echo "$(ts) [wt-setup] $wt has no flow.yaml; skip" >> "$log"
  exit 0
fi

submodules="$(python3 "$here/cfg.py" --project "$wt" workspace.submodules 2>/dev/null || true)"
if [ -n "$submodules" ] && [ "$submodules" != "null" ] && [ "$submodules" != "[]" ]; then
  echo "$(ts) [wt-setup] submodule init in $wt" >> "$log"
  git -C "$wt" submodule update --init --recursive >> "$log" 2>&1 || \
    echo "$(ts) [wt-setup] submodule init FAILED in $wt" >> "$log"
fi

setup="$(python3 "$here/cfg.py" --project "$wt" workspace.setup 2>/dev/null || true)"
if [ -z "$setup" ] || [ "$setup" = "null" ]; then
  echo "$(ts) [wt-setup] no workspace.setup for $wt; done" >> "$log"
  exit 0
fi

echo "$(ts) [wt-setup] run in $wt: $setup" >> "$log"
if (cd "$wt" && bash -lc "$setup") >> "$log" 2>&1; then
  echo "$(ts) [wt-setup] done: $wt" >> "$log"
else
  echo "$(ts) [wt-setup] FAILED: $wt (see log above)" >> "$log"
fi
exit 0
