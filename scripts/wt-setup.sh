#!/usr/bin/env bash
# PostToolUse[EnterWorktree] hook: prepare a freshly created worktree.
# Reads the hook payload from stdin, resolves the worktree dir, initialises
# submodules if the project declares any, then runs `workspace.setup` from
# .claude/omixflow/flow.yaml. Always exits 0: a PostToolUse hook must not block.
# The outcome reaches the session: `{git-dir}/omixflow-wt-setup.status` (`running` while it
# works, then `done` | `FAILED` and the tail of the error; Start reads it), and on a failure a JSON `additionalContext` the
# harness puts into the session's context right after EnterWorktree. SwAIS T-13: `pnpm install`
# failed (ERR_PNPM_UNSUPPORTED_ENGINE, Node 22 against `>=24`) and the session learned it only
# from a missing node_modules.
#
# Log: ~/.claude/omixflow-wt-setup.log

set -uo pipefail

log="${OMIXFLOW_WT_SETUP_LOG:-$HOME/.claude/omixflow-wt-setup.log}"   # the variable: tests
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

input="$(cat)"

# outcome: STATUS (done | FAILED), DETAIL (the tail of the error) → status file and, on FAILED, the context
report() {
  local status="$1" detail="$2" gitdir
  gitdir="$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null || true)"
  if [ -n "$gitdir" ] && [ -d "$gitdir" ]; then
    printf '%s\n%s\n' "$status" "$detail" > "$gitdir/omixflow-wt-setup.status"
  fi
  if [ "$status" = "FAILED" ]; then
    WT="$wt" DETAIL="$detail" LOG="$log" python3 -c 'import json, os
text = ("omixflow wt-setup FAILED in " + os.environ["WT"] + ": " + os.environ["DETAIL"]
        + " (log: " + os.environ["LOG"] + "). Dependencies are not installed: the gates will fail; "
        "Start stops at the deadlock point with this reason (protocol/worktree.md).")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))'
  fi
}
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

report running ""        # a hook killed on its timeout leaves `running`, not «no hook ran»
out_file="$(mktemp "${TMPDIR:-/tmp}/omixflow-wt-setup.XXXXXX")"
failed=""

# a step's output goes to a file, not `$(…)`: a process the setup leaves running with our stdout
# would hold the hook until it exits; the log gets the output after the step
run_step() {   # LABEL CMD
  local label="$1" cmd="$2" rc
  (cd "$wt" && bash -lc "$cmd") > "$out_file" 2>&1
  rc=$?
  cat "$out_file" >> "$log"
  if [ "$rc" -ne 0 ]; then
    echo "$(ts) [wt-setup] $label FAILED in $wt (see log above)" >> "$log"
    failed="${failed}${failed:+; }$label: $(grep -v '^[[:space:]]*$' "$out_file" | tail -n 8 | tr '\n' ' ')"
  fi
  return "$rc"
}

submodules="$(python3 "$here/cfg.py" --project "$wt" workspace.submodules 2>/dev/null || true)"
if [ -n "$submodules" ] && [ "$submodules" != "null" ] && [ "$submodules" != "[]" ]; then
  echo "$(ts) [wt-setup] submodule init in $wt" >> "$log"
  run_step "submodule init" "git submodule update --init --recursive" || true   # the setup still runs, as before 0.9.4
fi

setup="$(python3 "$here/cfg.py" --project "$wt" workspace.setup 2>/dev/null || true)"
if [ -z "$setup" ] || [ "$setup" = "null" ]; then
  echo "$(ts) [wt-setup] no workspace.setup for $wt" >> "$log"
else
  echo "$(ts) [wt-setup] run in $wt: $setup" >> "$log"
  run_step "$setup" "$setup" || true
fi
rm -f "$out_file"

if [ -n "$failed" ]; then
  echo "$(ts) [wt-setup] FAILED: $wt" >> "$log"
  report FAILED "$failed"
else
  echo "$(ts) [wt-setup] done: $wt" >> "$log"
  report done ""
fi
exit 0
