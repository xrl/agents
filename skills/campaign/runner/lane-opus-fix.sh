#!/usr/bin/env bash
# The Opus code-only fix for a pi lane's [hard] findings (DESIGN M4, A7: lane exit 10). Local
# `claude -p` in the same worktree, after the driver's turn has ended, so one writer at a time.
# On success run/result.json names the fix commit and the tick resumes the pi lane with
# `--integrate <sha>`; the driver then writes the witnesses.
#
#   lane-opus-fix.sh <step-dir> <worktree> <verify-file>
#
# Exit: 0 one fix commit on top | 20 no commit (run/handback.md) | 30 claude failed or timed out.
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
lane_setup "$1"
WT=$(cd "$2" && pwd -P); FINDINGS=$3
BEFORE=$(git -C "$WT" rev-parse HEAD)
P="$SR/prompts/opus-fix-${BEFORE:0:12}.txt"
cat >"$P" <<EOF
You are the Opus fixer for campaign step $STEP in worktree $WT. Fix only the findings tagged [hard] in $FINDINGS, as production code: no tests (the pi driver writes the witnesses next), one new commit on top, never an amend. Each finding names a defect and the behaviour that must hold; fix the defect and keep that behaviour, and do not delete code whose purpose you have not traced. A fix to unreleased work carries no Changelog: line. Every row of $EPOCH/EXECUTION.md §Rows and of the unit's DECISIONS.md is settled. Read $AGENTS_DIR/RUST_AGENT_RULES.md first. Run \`cargo fmt --all\` and \`cargo check --workspace --all-targets --locked\` before committing. Then end with one paragraph per finding: what you changed and why it holds.
EOF
OUT="$SR/opus-fix-${BEFORE:0:12}.json"
(cd "$WT" && timeout 3600 claude -p --model "${OPUS_MODEL:-claude-opus-5-5}" --output-format json --permission-mode dontAsk \
  --allowedTools "Read Grep Glob Edit Write Bash(cargo fmt:*) Bash(cargo check:*) Bash(cargo build:*) Bash(git status:*) Bash(git diff:*) Bash(git log:*) Bash(git show:*) Bash(git add:*) Bash(git commit:*)" \
  "$(cat "$P")" </dev/null >"$OUT") || { log_cost opus-fix "$OUT"; exit 30; }
log_cost opus-fix "$OUT"
AFTER=$(git -C "$WT" rev-parse HEAD)
[ "$AFTER" != "$BEFORE" ] || handback "The Opus fixer made no commit for $FINDINGS; its reply is in $OUT."
jq -n --arg sha "$AFTER" '{fix_sha: $sha}' >"$SR/result.json"
