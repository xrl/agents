#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
lane_setup "$1"
WT=$(cd "$2" && pwd -P); FINDINGS=$3
BEFORE=$(git -C "$WT" rev-parse HEAD)
P="$SR/prompts/opus-fix-${BEFORE:0:12}.txt"
cat >"$P" <<EOF
You are the Opus fixer for campaign step $STEP in worktree $WT. Fix only the findings tagged [hard] in $FINDINGS, as production code: no tests (the pi driver writes the witnesses next). Leave the changes uncommitted: this lane commits them as one new commit on top. Each finding names a defect and the behaviour that must hold; fix the defect and keep that behaviour, and do not delete code whose purpose you have not traced. A fix to unreleased work carries no Changelog: line. Every row of $EPOCH/EXECUTION.md §Rows and of the unit's DECISIONS.md is settled. Read $AGENTS_DIR/RUST_AGENT_RULES.md first. Run \`cargo fmt --all\` and \`cargo check --workspace --all-targets --locked\` before you end. Write git commands without quotes, backslashes, \$, backticks or braces; they are refused. End with one paragraph per finding: what you changed and why it holds.
EOF
OUT="$SR/opus-fix-${BEFORE:0:12}.json"
(cd "$WT" && timeout 3600 claude -p --restricted --strict-mcp-config --tools Read,Grep,Glob,Edit,Write,Bash \
  --model "${OPUS_MODEL:-claude-opus-5-5}" --output-format json --permission-mode dontAsk --settings "$LANE_SETTINGS" \
  --disallowedTools "Bash(git * --output*)" "Bash(*>*)" --add-dir "$EPOCH" "$AGENTS_DIR" \
  --allowedTools "Read Grep Glob Edit(./**) Write(./**) Bash(cargo fmt:*) Bash(cargo check:*) Bash(cargo build:*) Bash(git status:*) Bash(git diff:*) Bash(git log:*) Bash(git show:*)" \
  -- "$(cat "$P")" </dev/null >"$OUT") || { log_cost opus-fix "$OUT"; exit 30; }
log_cost opus-fix "$OUT"
[ "$(git -C "$WT" rev-parse HEAD)" = "$BEFORE" ] || handback "The Opus fixer moved HEAD past $BEFORE; it must leave its changes uncommitted. Its reply is in $OUT."
[ -n "$(git -C "$WT" status --porcelain)" ] || handback "The Opus fixer changed nothing for $FINDINGS; its reply is in $OUT."
{ printf '%s: fix the [hard] findings of %s\n\n' "$STEP" "${FINDINGS##*/}"; jq -r '.result // empty' "$OUT"; } >"$SR/opus-fix-msg.txt"
git -C "$WT" add -A && git -C "$WT" commit -q -F "$SR/opus-fix-msg.txt"
AFTER=$(git -C "$WT" rev-parse HEAD)
jq -n --arg sha "$AFTER" '{fix_sha: $sha}' >"$SR/result.json"
